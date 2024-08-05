import io
import logging
import socket
import json
import time
from PIL import Image, ImageFont, ImageDraw
from contextlib import asynccontextmanager
import asyncio
from fastapi import FastAPI, Depends, HTTPException
import uvicorn
import paho.mqtt.client as mqtt
from src.config_loader import ConfigLoader
from IT8951.display import AutoEPDDisplay
from IT8951 import constants

# Initialize logging
logging.basicConfig(level=logging.INFO)

# Configuration setup
config_loader = ConfigLoader()
app_config = config_loader.load()
mqtt_config = app_config.mqtt
device_config = app_config.device
screen_config = app_config.screen

# MQTT setup
mqtt_client = mqtt.Client()
status_topic = replace_device_id_placeholder(mqtt_config.topic_device_status)
image_topic = replace_device_id_placeholder(mqtt_config.topic_image_display)

# Global variables
image_rotate = 0
display = None

# Helper functions
def replace_device_id_placeholder(topic: str):
    return topic.replace(mqtt_config.device_id_placeholder, device_config.id)

def set_rotate(width, height, rotate=0):
    if (rotate / 90) % 2 == 1:
        width, height = height, width
    return width, height

def get_mqtt_client():
    return mqtt_client

async def publish_periodically(client: mqtt.Client):
    while True:
        await asyncio.sleep(60)
        client.publish(status_topic, get_status_payload("online"))

def get_status_payload(status):
    hostname = socket.gethostname()
    ip_address = get_ip()
    return json.dumps({
        "hostname": hostname,
        "ip_address": ip_address,
        "mac": device_config.id,
        'status': status,
        'wired': True,
        'battery': 100,
        'timestamp': time.time()
    })

def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0)
    try:
        s.connect(('10.254.254.254', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

async def start_background_tasks():
    task = asyncio.create_task(publish_periodically(mqtt_client))
    return task

def _place_text(img, text, x_offset=0, y_offset=0):
    fontsize = 80
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype('/usr/share/fonts/truetype/freefont/FreeSans.ttf', fontsize)
    except OSError:
        font = ImageFont.truetype('/usr/share/fonts/TTF/DejaVuSans.ttf', fontsize)

    img_width, img_height = img.size
    text_width = font.getlength(text)
    text_height = fontsize
    draw_x = (img_width - text_width) // 2 + x_offset
    draw_y = (img_height - text_height) // 2 + y_offset
    draw.text((draw_x, draw_y), text, font=font)

async def display_image_on_epd(display_image):
    global display
    if display is None:
        raise HTTPException(status_code=500, detail="Display not initialized")

    try:
        partial_update(display)
    except Exception as e:
        logging.error(f"Error displaying image on e-ink screen: {e}")

def partial_update(display):
    if display is None:
        logging.error("Display object is None. Cannot perform partial update.")
        return

    try:
        print('Starting partial update...')
        display.frame_buf.paste(0xFF, box=(0, 0, display.width, display.height))
        print('  writing full...')
        _place_text(display.frame_buf, 'partial', x_offset=-display.width//4)
        display.draw_full(constants.DisplayModes.GC16)

        print('  writing partial...')
        _place_text(display.frame_buf, 'update', x_offset=+display.width//4)
        display.draw_partial(constants.DisplayModes.DU)
    except Exception as e:
        logging.error(f"Error during partial update: {e}")

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logging.info("Connected to MQTT Broker!")
    else:
        logging.error(f"Failed to connect, return code {rc}")

def on_message(client, userdata, msg):
    logging.info(f"Received from `{msg.topic}` topic")
    try:
        image_data = Image.open(io.BytesIO(msg.payload))
        asyncio.create_task(display_image_on_epd(image_data))
    except Exception as e:
        logging.error(f"Error decoding and displaying the image: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    global display
    logging.info("lifespan start - startup")
    try:
        display = AutoEPDDisplay(vcom=-2.27, rotate=None, mirror=False, spi_hz=24000000)
        logging.info(f"EPD initialized with size: {display.width}x{display.height}")

        mqtt_client.username_pw_set(mqtt_config.username, mqtt_config.password)
        mqtt_client.tls_set()
        mqtt_client.connect(mqtt_config.broker, mqtt_config.port, 60)
        mqtt_client.on_message = on_message
        mqtt_client.on_connect = on_connect
        mqtt_client.loop_start()
        mqtt_client.subscribe(image_topic)
        logging.info("Subscribed to image topic:" + image_topic)

        await start_background_tasks()
        yield
    except Exception as e:
        logging.error(f"Exception during lifespan: {e}")
        raise
    finally:
        logging.info("lifespan end - shutdown")
        mqtt_client.loop_stop()
        mqtt_client.disconnect()

app = FastAPI(lifespan=lifespan)

@app.get("/some-endpoint")
async def some_endpoint():
    if display is None:
        raise HTTPException(status_code=500, detail="Display not initialized")
    try:
        await asyncio.to_thread(partial_update, display)
        return {"status": "ok"}
    except Exception as e:
        logging.error(f"Exception during /some-endpoint: {e}")
        raise HTTPException(status_code=500, detail="Failed to update display")

@app.get("/config")
async def root():
    app_config_without_password = app_config.copy()
    app_config_without_password.mqtt.password = "********"
    return app_config_without_password

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
