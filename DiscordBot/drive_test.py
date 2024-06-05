import requests
import io
from PIL import Image, ImageFilter, UnidentifiedImageError
from bs4 import BeautifulSoup

link  = 'https://drive.google.com/file/d/1OxltVnSJdTGF6LWwapPTfcwwkxP1AQbG/view'

response = requests.get(link)

base_url = "https://drive.google.com/uc?export=download"
session = requests.Session()

# Fetch the download link
response = session.get(link, stream=True)
soup = BeautifulSoup(response.content, "html.parser")

# Check if a confirmation token is required
confirm_token = None
for input_tag in soup.find_all("input"):
    if input_tag.get("name") == "confirm":
        confirm_token = input_tag.get("value")
        break

if confirm_token:
    print('here')
    # If a confirmation token is found, use it to get the file
    response = session.get(f"{base_url}&confirm={confirm_token}&id={file_id}", stream=True)

# Download the image
with open('test.png', "wb") as file:
    for chunk in response.iter_content(32768):
        if chunk:
            file.write(chunk)

print(f"Image downloaded to {'test.png'}")