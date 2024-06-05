# bot.py
import discord
from discord.ext import commands
import os
import json
import logging
import re
import requests
from report import Report
import pdb
from moderator import ModReport
from PIL import Image, ImageFilter, UnidentifiedImageError
import io
from urllib.parse import urlparse
from image_utils import *
from copy import deepcopy

# Set up logging to the console
logger = logging.getLogger('discord')
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)

# There should be a file called 'tokens.json' inside the same folder as this file
token_path = 'tokens.json'
if not os.path.isfile(token_path):
    raise Exception(f"{token_path} not found!")
with open(token_path) as f:
    # If you get an error here, it means your token is formatted incorrectly. Did you put it in quotes?
    tokens = json.load(f)
    discord_token = tokens['discord']


class ModBot(discord.Client):
    def __init__(self): 
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='.', intents=intents)
        self.group_num = None
        self.mod_channels = {} # Map from guild to the mod channel id for that guild
        self.reports = {} # Map from user IDs to the state of their report
        self.mod_reports = {}
        
        self.awaiting_mod_decisions = {1: {}, 2: {}, 3:{}, 4:{}, 5:{}, 6:{}, 'NOT_AI': {}} # Maps from abuse types to a list of tuples containing report id, the message object, and images
        self.caseno_to_info = {} # Maps from report id to a tuple defined below
        self.most_recent = None
        self.deepfake_urls = []
        self.deepfake_images = []
        
        self.mod_channel = None

    async def on_ready(self):
        print(f'{self.user.name} has connected to Discord! It is these guilds:')
        for guild in self.guilds:
            print(f' - {guild.name}')
        print('Press Ctrl-C to quit.')
        
        self.mod_channel = discord.utils.get(guild.text_channels, name = 'group-11-mod')
        # Parse the group number out of the bot's name
        match = re.search('[gG]roup (\d+) [bB]ot', self.user.name)
        if match:
            self.group_num = match.group(1)
        else:
            raise Exception("Group number not found in bot's name. Name format should be \"Group # Bot\".")

        # Find the mod channel in each guild that this bot should report to
        for guild in self.guilds:
            for channel in guild.text_channels:
                if channel.name == f'group-{self.group_num}-mod':
                    self.mod_channels[guild.id] = channel
                    print(channel)
        

    async def on_message(self, message):
        '''
        This function is called whenever a message is sent in a channel that the bot can see (including DMs). 
        Currently the bot is configured to only handle messages that are sent over DMs or in your group's "group-#" channel. 
        '''
        # Ignore messages from the bot 
        if message.author.id == self.user.id:
            return
        # await self.blur_image(message)
        # Check if this message was sent in a server ("guild") or if it's a DM
        
        if message.guild and message.guild.id in self.mod_channels:
            await self.handle_mod_message(message)
        
        if message.guild:
            package = await self.handle_channel_message(message)
            # if changed or deleted, send the message to the mod channel
            if package:
                start = '=' * 20 + '\n'
                start += f'The following message had images blurred or deleted due to automated moderation:\n'
                author = f'Author: {message.author.display_name} ({message.author.mention})\n'
                content = f'Content: {message.content}\n'
                
                await self.mod_channel.send(start + author + content)
                if message.attachments:
                    for attachment in message.attachments:
                        await self.mod_channel.send(file = await attachment.to_file())
                
                await self.mod_channel.send('Please review the message and take appropriate action.\n') 
                await self.mod_channel.send('=' * 20)
                    
        else:
            await self.handle_dm(message)

    async def handle_dm(self, message):
        # Handle a help message
        if message.content == Report.HELP_KEYWORD:
            reply =  "Use the `report` command to begin the reporting process.\n"
            reply += "Use the `cancel` command to cancel the report process.\n"
            await message.channel.send(reply)
            return

        author_id = message.author.id
        author = message.author

        responses = []

        # Only respond to messages if they're part of a reporting flow
        if author_id not in self.reports and not message.content.startswith(Report.START_KEYWORD):
            return

        # If we don't currently have an active report for this user, add one
        if author_id not in self.reports:
            self.reports[author_id] = Report(self)

        # Let the report class handle this message; forward all the messages it returns to uss
        responses = await self.reports[author_id].handle_message(message)
        for r in responses:
            await message.channel.send(r)

        # If the report is complete or cancelled, remove it from our map
        if self.reports[author_id].report_complete():
            
            if self.reports[author_id].requires_forwarding:
                msg = self.reports[author_id].message
                mod_channel = self.mod_channels[msg.guild.id]
                start_message = '=' * 20 + '\n'
                start_message += '****REPORT START****\n' 
                start_message += f'REPORT ID: {self.reports[author_id].report_no}\n'
                start_message += f"Forwarded report from {author}\n"
                start_message += f"Message text: {msg.content}\n"
                start_message += f'Author of the message: {msg.author.name}\n'
                start_message += f"Abuse type: {self.reports[author_id].forward_abuse_string}\n"
                if self.reports[author_id].specific_abuse_string:
                    start_message += f"Specific abuse: {self.reports[author_id].specific_abuse_string}\n"
                if not self.reports[author_id].keep_AI:
                    start_message += "The user would like to not see AI-generated content anymore.\n"
                
                image = None
                if msg.attachments:
                    attachment = msg.attachments[0]  # Assuming the first attachment is the image
                    start_message += 'Image associated with the message attached:\n'
                    image = attachment
                elif msg.embeds:
                    embed = msg.embeds[0]
                    start_message += 'Embed associated with the message attached:\n'
                    image = embed
                # end_message = f'MODERATORS PLEASE SELECT 1. Ignore 2. Warn 3. Delete 4. Ban 5. Delete + Warn 6. Delete + Ban\n'
                end_message = '****REPORT END****\n'
                end_message += '=' * 20
                """
                end_message += 'Please type the number corresponding to the type of abuse you see in the message.\n'
                end_message += '1. Imminent Danger\n'
                end_message += '2. Spam\n'
                end_message += '3. Nude or Graphic Media\n'
                end_message += '4. Disinformation\n'
                end_message += '5. Hate speech/harrassment\n'
                end_message += '6. Other(including including satire, memes, commentary, couterspeech, etc.)'
                """
                
                # maps from abuse type ot report number to a tuple of the starting message we send to the mod server, images, the ending message for the mod server, and the actual message in question.
                # the last two are for ease of cleaning up the report dicionary once it is handled.
                self.awaiting_mod_decisions[self.reports[author_id].abuse_type][self.reports[author_id].report_no] = (start_message, image, end_message, msg, self.reports[author_id].abuse_type, self.reports[author_id].report_no)
                self.caseno_to_info[self.reports[author_id].report_no] = (start_message, image, end_message, msg, self.reports[author_id].abuse_type, self.reports[author_id].report_no)
                
                self.most_recent = (start_message, image, end_message, msg, self.reports[author_id].abuse_type, self.reports[author_id].report_no)
                
                update = f'There was a new report added to the queue for review. There are now {len(self.caseno_to_info)} report(s) in the queue. Please type `start` to begin reviewing the reports.'
                await mod_channel.send(update)
            
            self.reports.pop(author_id)

    async def handle_channel_message(self, message):
        # Only handle messages sent in the "group-#" channel
        if not message.channel.name == f'group-{self.group_num}':
            return
        return await self.eval_text(message)

    
    async def handle_mod_message(self, message):
        # will handle the moderators' decisions
        if not message.channel.name == f'group-{self.group_num}-mod':
            return
        
        author_id = message.author.id
        author = message.author
        
        if message.author.id == self.user.id:
            return

        # Only respond to messages if they're part of a reporting flow
        if author_id not in self.mod_reports and not message.content.startswith(ModReport.START_KEYWORD):
            return

        # If we don't currently have an active report for this user, add one
        if author_id not in self.mod_reports:
            self.mod_reports[author_id] = ModReport(self)
        
        response = await self.mod_reports[author_id].handle_message(message, self.awaiting_mod_decisions, self.caseno_to_info, self.most_recent)
        
        if response:
            for r in response:
                if type(r) == str:
                    await message.channel.send(r)
                else:
                    await message.channel.send(file = r)
        else:
            await message.channel.send("I'm sorry, I didn't understand that command. Please type `start` and then `help` for more information.")
        
        if self.mod_reports[author_id].report_complete():
            self.awaiting_mod_decisions[self.caseno_to_info[self.mod_reports[author_id].report_no][-2]].pop(self.mod_reports[author_id].report_no)
            self.caseno_to_info.pop(self.mod_reports[author_id].report_no)
            if self.most_recent[5] == self.mod_reports[author_id].report_no:
                self.most_recent = None
                # Find the most recent report
                for key in self.caseno_to_info:
                    if not self.most_recent or int(self.caseno_to_info[key][-1][1:]) > int(self.most_recent[-1][1:]):
                        self.most_recent = self.caseno_to_info[key]

            if self.mod_reports[author_id].delete:
                await self.mod_reports[author_id].message.delete()
            if self.mod_reports[author_id].blur:
                await blur_all_images(self.mod_reports[author_id].message)
            self.mod_reports.pop(author_id)
        
        elif self.mod_reports[author_id].report_cancelled():
            self.mod_reports.pop(author_id)
            

    async def eval_text(self, message):
        ''''
        TODO: Once you know how you want to evaluate messages in your channel, 
        insert your code here! This will primarily be used in Milestone 3. 
        '''
        # original = deepcopy(message)
        package = await self.auto_handle(message)
        
        return package
    
    
    async def auto_handle(self, message):
        """
        This function will blur the image present in a message.
        """

        urls = extract_urls(message.content)
        if message.author.id == self.user.id:
            return False

        if not message.attachments and not urls:
            logger.info('No attachments or urls found')
            return False
        
        violent_or_adult = False
        edited = False
        delete = False
        
        original_content = message.content
        blurred_images = []
        original_image_urls = []
        original_content = message.content
        original_author = message.author
        original_author_info = f"Originally sent by {original_author.display_name} ({original_author.mention}). URL's have been obfuscated."
        
        # Check for deepfake images in attachments
        for attachment in message.attachments:
            if any(attachment.filename.lower().endswith(ext) for ext in ['png', 'jpg', 'jpeg', 'gif']):
                try:
                # Get the image data from the attachment
                    image_data = await attachment.read()
                    
                    discord_file, change = process_image_data(image_data, attachment.filename, attachment.url)
                    
                    edited = edited or change
                    if discord_file:
                        blurred_images.append(discord_file)
                        original_image_urls.append(attachment.url)
                        logger.info('Created discord file and appended image URL')
                    elif  (not discord_file and change):
                        violent_or_adult = True
                    else:
                        pass
                except Exception as e:
                    logger.error(f"Error processing attachment: {e}")
        
        # Check for deepfake images in urls
        for url in urls:
            is_image, extension = is_image_url(url)
            if is_image:
                try:
                    # Get the image data from the URL
                    if "drive.google.com" in url:
                        file_id = url.split('/d/')[1].split('/')[0]
                        url = f"https://drive.google.com/uc?export=download&id={file_id}"
                    image_data = requests.get(url).content
                    parsed_url = urlparse(url)
                    filename = parsed_url.path.split("/")[-1] if parsed_url.path.split("/")[-1] else f'image.{extension}'
                    discord_file, change = process_image_data(image_data, filename, url)
                    edited = edited or change
                    if discord_file or (not discord_file and change):
                        blurred_images.append(discord_file)
                        original_image_urls.append(url)
                        logger.info('Created discord file and appended image URL')
                    elif (not discord_file and change):
                        violent_or_adult = True
                    else:
                        pass
                except requests.exceptions.RequestException as e:
                    logger.error(f"Error downloading image from URL: {e}")
       
        
        new_content = original_content
        # Obfuscate deepfake urls            
        for url in original_image_urls:
            obfuscated_url = obfuscate_url(url)
            new_content = original_content.replace(url, obfuscated_url)

        if edited and (blurred_images or violent_or_adult):
            logger.info('Deleted message')
            links = '\n'.join([f"[Image {i+1}](<{url}>)" for i, url in enumerate(original_image_urls)])
            
            try:
                await message.delete()
            except discord.errors.Forbidden:
                print(f"Failed to delete message from {message.author} in {message.channel} due to insufficient permissions.")
            except discord.errors.NotFound:
                print(f"Message from {message.author} in {message.channel} was not found (possibly already deleted).")
            except discord.errors.HTTPException as e:
                print(f"Failed to delete message from {message.author} in {message.channel} due to HTTP error: {e}")

            # Send the blurred images with the original message content in the same channel
            try:
                await message.channel.send(content=original_author_info)
                if violent_or_adult:
                    await message.channel.send(content = 'This message has been edited due to the presence of adult or violent content. The image(s) have been blurred or deleted. Deleted photos will not be relinked.')
                await message.channel.send(content=new_content, files=blurred_images)
                await message.channel.send('Original Image(s) linked below:\n' + links)
            except discord.HTTPException as e:
                logger.error(f"Error sending message: {e}")
                return True
            logger.info('Sent message')
        return violent_or_adult or edited

    def code_format(self, text):
        ''''
        TODO: Once you know how you want to show that a message has been 
        evaluated, insert your code here for formatting the string to be 
        shown in the mod channel. 
        '''
        return "Evaluated: '" + text+ "'"

client = ModBot()
client.run(discord_token)
