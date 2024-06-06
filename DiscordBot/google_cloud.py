from google.cloud import vision
import io
from PIL import Image, ImageFilter
import os

os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'application_default_credentials.json'

def detect_safe_search(image):
    from google.cloud import vision

    client = vision.ImageAnnotatorClient()

    image = vision.Image(content=image)
    response = client.safe_search_detection(image=image)
    safe = response.safe_search_annotation

    # Names of likelihood from google.cloud.vision.enums
    likelihood_name = (
        "UNKNOWN",
        "VERY_UNLIKELY",
        "UNLIKELY",
        "POSSIBLE",
        "LIKELY",
        "VERY_LIKELY",
    )
    print("Safe search:")

    print(f"adult: {likelihood_name[safe.adult]}")
    print(f"medical: {likelihood_name[safe.medical]}")
    print(f"spoofed: {likelihood_name[safe.spoof]}")
    print(f"violence: {likelihood_name[safe.violence]}")
    print(f"racy: {likelihood_name[safe.racy]}")

    if response.error.message:
        raise Exception(
            "{}\nFor more info on error messages, check: "
            "https://cloud.google.com/apis/design/errors".format(response.error.message)
        )
    
    return likelihood_name[safe.adult], likelihood_name[safe.violence], likelihood_name[safe.spoof]
