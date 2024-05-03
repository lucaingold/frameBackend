import io
import logging
from omni_epd import displayfactory, EPDNotFoundError
import threading
import time
from PIL import Image, ImageEnhance

DISPLAY_TYPE = "waveshare_epd.it8951"


class EInkScreen:
    def __init__(self, screen_width=1600, screen_height=1200, brightness_factor=1.0, darkness_threshold=0.5):
        # Config Dictionary for omni-epd
        self.config_dict = {}

        # EPD
        self.epd = None

        # Image
        self.image_base = None
        self.image_display = None
        self.width = screen_width
        self.height = screen_height

        self.lock = threading.Lock()

        self.brightness_factor = brightness_factor
        self.darkness_threshold = darkness_threshold

    pass

    def run(self):
        logging.info("einkframe has started")
        try:
            self.epd = displayfactory.load_display_driver(DISPLAY_TYPE, self.config_dict)
            self.epd.width = self.width
            self.epd.height = self.height
            image_rotate = 0
            # Set width and height for einkframe program
            self.width, self.height = self.set_rotate(self.epd.width, self.epd.height, image_rotate)
        except EPDNotFoundError:
            logging.error(f"Couldn't find {DISPLAY_TYPE}")
            exit()

        except KeyboardInterrupt:
            logging.info("ctrl + c:")
            exit()

        except BaseException as e:
            logging.error(e)
            exit()

    pass

    def display_image(self, image_data):
        try:
            with self.lock:
                # brightened_img = self.enhance_brightness(image_data)
                self.display_image_on_epd(image_data)
                time.sleep(5)
        except Exception as e:
            logging.error("Error decoding and displaying the image:", str(e))

    # def enhance_brightness(self, img):
    #     logging.info("Increase brightness by %s", str(self.brightness_factor))
    #     enhancer = ImageEnhance.Brightness(img)
    #     return enhancer.enhance(self.brightness_factor)

    def enhance_brightness(self, img):
        # Measure darkness of the image
        img_gray = img.convert('L')
        histogram = img_gray.histogram()
        pixels = sum(histogram)
        brightness = sum(index * value for index, value in enumerate(histogram)) / pixels

        # If the proportion of dark pixels is below the threshold, increase brightness
        logging.info("Image details - effective brightness: %s, darkness_threshold: %s, brightness_factor: %s",
                     str(brightness), str(self.darkness_threshold), str(self.brightness_factor))
        if brightness < self.darkness_threshold:
            brightness_factor = self.adjust_brightness_factor(brightness)
            logging.info("Increase brightness by %s", str(brightness_factor))
            enhancer = ImageEnhance.Brightness(img)
            img = enhancer.enhance(self.brightness_factor)

        return img

    def adjust_brightness_factor(self, brightness):
        if brightness <= 100:
            return self.brightness_factor + 0.2
        elif 100 < brightness < 105:
            return self.brightness_factor
        else:
            return self.brightness_factor - 0.2

    def display_image_on_epd(self, display_image):
        self.image_display = display_image.copy()
        logging.info("Prepare e-ink screen")
        self.epd.prepare()
        logging.info("Clear e-ink screen")
        self.epd.clear()
        logging.info("Display image on e-ink screen")
        self.epd.display(self.image_display)
        logging.info("Send e-ink screen to sleep")
        self.epd.sleep()
        self.epd.close()
        return

    @staticmethod
    def set_rotate(width, height, rotate=0):
        if (rotate / 90) % 2 == 1:
            temp = width
            width = height
            height = temp
        return width, height
