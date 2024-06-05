import json
import re
import requests
import logging
import io
from PIL import Image, ImageFilter, UnidentifiedImageError
import discord
from urllib.parse import urlparse
from google_cloud import detect_safe_search
from skimage import io as skio, img_as_ubyte
from skimage.filters import gaussian
import numpy as np

logger = logging.getLogger('discord')
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)

def is_deepfake(image_url):
    """
    This function makes an API call to AIORNOT which checks if the image in the passed url is a deepfake
    """

    api_url = "https://api.aiornot.com/v1/reports/image"
    AIORNOT_API_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6IjM1MGUxYjA3LWNlYjctNDMxNS1hNjUyLTU2Mjg0YTk2MzBhMyIsInVzZXJfaWQiOiIzNTBlMWIwNy1jZWI3LTQzMTUtYTY1Mi01NjI4NGE5NjMwYTMiLCJhdWQiOiJhY2Nlc3MiLCJleHAiOjAuMH0.Hyg8WHNEQTi328xxGkM-KrZkoNkopmaJcX9L95iD0qM'

    headers = {
        'Authorization': f'Bearer {AIORNOT_API_KEY}',
        'Content-Type': 'application/json',
            'Accept': 'application/json'
    }

    payload = json.dumps({
        "object": image_url
    })
    try:
        response = requests.request("POST", api_url, headers=headers, data=payload)
    except Exception as e:
        return False, f'An unexpected error occurred: {e}'
    try:
        response = response.json()
    except json.JSONDecodeError as json_err:
        return False, f'Error decoding JSON response: {json_err}'
    except Exception as e:
        return False, f'An unexpected error occurred while decoding JSON: {e}'

    is_deep_fake = response.get("report",{}).get("ai",{}).get("is_detected", False)
    return is_deep_fake, None

def extract_urls(message_content):
    url_pattern = re.compile(r'(https?://[^\s]+)')
    urls = url_pattern.findall(message_content)
    return urls

def is_image_url(url):
    try:
        response = requests.head(url, allow_redirects=True)
        content_type = response.headers.get('Content-Type')
        if content_type and content_type.startswith('image/'):
            return True, content_type.split('/')[-1]  # Return True and the image extension
        return False, None
    except requests.RequestException as e:
        logger.error(f"Error checking URL content type: {e}")
        return False, None
    
def process_image_data(image_data, filename, image_url):
    try:
        image = Image.open(io.BytesIO(image_data))
        # print(type(image))
        # image = image_data
        logger.info('Opened image')

        # Check if image is a deepfake
        is_deepFake, error_message = is_deepfake(image_url)
        
        if is_deepFake:
            logger.info("Deepfake Detected")
            # Apply a blur filter
            
            adult, violence = detect_safe_search(image_data)
            
            if adult == 'VERY_LIKELY' or violence == 'VERY_LIKELY':
                logger.info("Adult content detected")
                return None, True
            if adult == 'LIKELY' or violence == 'LIKELY':
                
                blurred_image = image.copy()
                blurred_image = blurred_image.filter(ImageFilter.GaussianBlur(15))
                
                # Save the blurred image to a BytesIO object
                blurred_image_bytes = io.BytesIO()
                blurred_image.save(blurred_image_bytes, format=image.format)
                blurred_image_bytes.seek(0)
                logger.info('Saved image')

                # Create a discord.File from the blurred image
                discord_file = discord.File(fp=blurred_image_bytes, filename=f'blurred_{filename}', spoiler=False)
                return discord_file, True
            else:
                return discord.File(fp=io.BytesIO(image_data), filename=filename, spoiler=False), False
        logger.error(error_message)
    except UnidentifiedImageError:
        logger.error(f"Could not identify image file: {filename}")
    except Exception as e:
        logger.error(f"Error processing image: {e}")
    return None

def obfuscate_url(url):
    return url.replace('.', '[dot]').replace('http', 'hxxp')

async def blur_all_images(message):
    
    urls = extract_urls(message.content)
        
    if not message.attachments and not urls:
        logger.info('No attachments or urls found')
        return None

    original_content = message.content
    blurred_images = []
    original_image_urls = []
    original_content = message.content
    original_author = message.author
    original_author_info = f"Originally sent by {original_author.display_name} ({original_author.mention}). All images have been blurred as prescribed by the moderator team."

    for attachment in message.attachments:
        if any(attachment.filename.lower().endswith(ext) for ext in ['png', 'jpg', 'jpeg', 'gif']):
            try:
            # Get the image data from the attachment
                image_data = await attachment.read()
                discord_file = process_image_data_old(image_data, attachment.filename)
                if discord_file:
                    blurred_images.append(discord_file)
                    original_image_urls.append(attachment.url)
                    logger.info('Created discord file and appended image URL')
            except Exception as e:
                logger.error(f"Error processing attachment: {e}")
    
    for url in urls:
        is_image, extension = is_image_url(url)
        if is_image:
            try:
                # Get the image data from the URL
                image_data = requests.get(url).content
                parsed_url = urlparse(url)
                # filename = url.split("/")[-1]
                filename = parsed_url.path.split("/")[-1] if parsed_url.path.split("/")[-1] else f'image.{extension}'
                discord_file = process_image_data_old(image_data, filename)
                if discord_file:
                    blurred_images.append(discord_file)
                    original_image_urls.append(url)
                    logger.info('Created discord file and appended image URL')
            except requests.exceptions.RequestException as e:
                logger.error(f"Error downloading image from URL: {e}")
    for url in original_image_urls:
        obfuscated_url = obfuscate_url(url)
        original_content = original_content.replace(url, obfuscated_url)
    if blurred_images:
        try:
            await message.delete()
        except discord.HTTPException as e:
            logger.error(f"Error deleting message: {e}")
            return
        # print('Deleted message')
        logger.info('Deleted message')
        links = '\n'.join([f"[Image {i+1}](<{url}>)" for i, url in enumerate(original_image_urls)])
        # for url in original_image_urls:
        #     original_content = original_content.replace(url, f"<{url}>")
        # Send the blurred images with the original message content in the same channel
        try:
            await message.channel.send(content=original_author_info)
            await message.channel.send(content=original_content, files=blurred_images)
            await message.channel.send('Original Image(s) linked below:\n' + links)
        except discord.HTTPException as e:
            logger.error(f"Error sending message: {e}")
            return
        # print('Sent message')
        logger.info('Sent message')
        

def process_image_data_old(image_data, filename):
    try:
        image = Image.open(io.BytesIO(image_data))
        logger.info('Opened image')

        # Apply a blur filter
        blurred_image = image.filter(ImageFilter.GaussianBlur(15))
        logger.info('Blurred image')

        # Save the blurred image to a BytesIO object
        blurred_image_bytes = io.BytesIO()
        blurred_image.save(blurred_image_bytes, format=image.format)
        blurred_image_bytes.seek(0)
        logger.info('Saved image')

        # Create a discord.File from the blurred image
        discord_file = discord.File(fp=blurred_image_bytes, filename=f'blurred_{filename}', spoiler=False)
        return discord_file
    except UnidentifiedImageError:
        logger.error(f"Could not identify image file: {filename}")
    except Exception as e:
        logger.error(f"Error processing image: {e}")
    return None
    
    