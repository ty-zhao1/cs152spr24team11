from enum import Enum, auto
import discord
import re

SPECIFIC_OPTIONS = {
    1: "Please select the type of imminent danger you see: 1. Credible threat of violence, 2. Suicidal content or self-harm.",
    2: "Please select the type of spam you see: 1. Fraud, 2. Solicitation, 3. Impersonation.",
    4: "Please select the type of disinformation you see: 1. Targeted at political candidates/figures, 2. Imposter, 3. False context, 4. Fabricated content,",
    5: "Please select the type of hate speech/harrassment you see: 1. Bullying, 2. Hate speech directed at me/specific group of people, 3. Unwanted sexual content, 4. Revealing Private Information.",
}

CLOSING_MESSAGES = {
    1: ["Thank you for reporting. Our content moderation team will review the report and decide on the appropriate response, notifying local authorities if necessary."],
    2: ['Thank you for reporting. Our content moderation team will review the report and decide on the appropriate response, notifying local authorities if necessary.'],
    3: ['Thank you for reporting. Our content moderation team will review this report and will take appropriate steps to flag, censor,  or remove this content.'],
    4: ['Thank you for reporting. Our content moderation team will review the report and decide on the appropriate actions. This may include flagging of the content as AI-generated.\n Would you like us to remove all detected AI-generated content in from your feed the future?'],
    5: ['Thank you for reporting. Our content moderation team will review the report and decide on the appropriate actions. This may include flagging of the content as AI-generated.\n Would you like us to remove all detected AI-generated content in from your feed the future?'],
    6: ["Thank you for reporting. This content does not violate our policy as it does not cause significant confusion about the authenticity of the media."]
}

class State(Enum):
    REPORT_START = auto()
    AWAITING_MESSAGE = auto()
    MESSAGE_IDENTIFIED = auto()
    REPORT_COMPLETE = auto()
    
    AWAIT_CONTENT_TYPE = auto()
    AWAIT_SPECIFIC_TYPE = auto()
    
    AWAIT_AI_REMOVAL = auto()
    
    # ADD MORE STATES HERE FOR DIFFERENT FLOW STUFF

class Report:
    START_KEYWORD = "report"
    CANCEL_KEYWORD = "cancel"
    HELP_KEYWORD = "help"

    def __init__(self, client):
        self.state = State.REPORT_START
        self.client = client
        self.message = None
        
        # 1 is Imminent Danger, 2 is Spam, 3 is Nudity or Graphic, 4 is Disinformation, 5 is Hate speech/harrassment, 6 is Other
        self.abuse_type = None
        
    
    async def handle_message(self, message):
        '''
        This function makes up the meat of the user-side reporting flow. It defines how we transition between states and what 
        prompts to offer at each of those states. You're welcome to change anything you want; this skeleton is just here to
        get you started and give you a model for working with Discord. 
        '''

        if message.content == self.CANCEL_KEYWORD:
            self.state = State.REPORT_COMPLETE
            return ["Report cancelled."]
        
        if self.state == State.REPORT_START:
            reply =  "Thank you for starting the reporting process. "
            reply += "Say `help` at any time for more information.\n\n"
            reply += "Please copy paste the link to the message you want to report.\n"
            reply += "You can obtain this link by right-clicking the message and clicking `Copy Message Link`."
            self.state = State.AWAITING_MESSAGE
            return [reply]
        
        if self.state == State.AWAITING_MESSAGE:
            # Parse out the three ID strings from the message link
            m = re.search('/(\d+)/(\d+)/(\d+)', message.content)
            if not m:
                return ["I'm sorry, I couldn't read that link. Please try again or say `cancel` to cancel."]
            guild = self.client.get_guild(int(m.group(1)))
            if not guild:
                return ["I cannot accept reports of messages from guilds that I'm not in. Please have the guild owner add me to the guild and try again."]
            channel = guild.get_channel(int(m.group(2)))
            if not channel:
                return ["It seems this channel was deleted or never existed. Please try again or say `cancel` to cancel."]
            try:
                message = await channel.fetch_message(int(m.group(3)))
            except discord.errors.NotFound:
                return ["It seems this message was deleted or never existed. Please try again or say `cancel` to cancel."]

            # Here we've found the message - it's up to you to decide what to do next!
            self.state = State.AWAIT_CONTENT_TYPE
            # return ["I found this message:", "```" + message.author.name + ": " + message.content + "```", \
            #         "This is all I know how to do right now - it's up to you to build out the rest of my reporting flow!"]
            # return ["I found this message:", "```" + message.author.name + ": " + message.content + "```", \
            #         "if you want to report, please specify the type of AI-generated content you see."] \
            return   [' You can select from 1. Imminent Danger, 2. Spam, 3. Nudity or Graphic, 4. Disinformation, 5. Hate speech/harrassment, 6. Other (including satire, memes, commentary, couterspeech, etc.)'] \
                            + ['Please type the number of the content type you see.']

            
        # this block determines the type of abuse the user is reporting
        # for numbering see comments in init
        if self.state == State.AWAIT_CONTENT_TYPE:
            try:
                selection = int(message.content)
                self.abuse_type = selection
            except:
                return ["Please type the number of the content type you see."]
            
            if self.abuse_type not in SPECIFIC_OPTIONS:
                self.state = State.REPORT_COMPLETE
                curr_abuse = self.abuse_type
                self.abuse_type = None
                if curr_abuse == 3:
                    # TODO: insert code here to actually send to moderation team
                    return CLOSING_MESSAGES[curr_abuse]
                elif curr_abuse == 6:
                    # TODO: insert code here to actually send to moderation team
                    return CLOSING_MESSAGES[curr_abuse]
            else:
                self.state = State.AWAIT_SPECIFIC_TYPE
                return [SPECIFIC_OPTIONS[self.abuse_type]]

        # this block zones in on the specific type of abuse the user is reporting
        if self.state == State.AWAIT_SPECIFIC_TYPE:
            try:
                selection = int(message.content)
            except:
                return [SPECIFIC_OPTIONS[self.abuse_type]]
            
            if (selection > 2 and self.abuse_type == 1) or (selection > 3 and self.abuse_type == 2 ) or (selection > 4 and self.abuse_type >=3):
                return ["Please type a valid number of the content type you see."]
            
            if self.abuse_type == 4 or self.abuse_type == 5:
                self.state = State.AWAIT_AI_REMOVAL
                curr_abuse = self.abuse_type
                self.abuse_type = None
            else:
                self.state = State.REPORT_COMPLETE
                curr_abuse = self.abuse_type
                self.abuse_type = None
            
            # TODO: insert code here to actually send to moderation team
            return CLOSING_MESSAGES[curr_abuse]
            
        # this block implements the AI removal feature
        if self.state == State.AWAIT_AI_REMOVAL:
            try:
                selection = message.content.lower()
            except:
                return ["Please type yes or no."]
            
            self.state = State.REPORT_COMPLETE
            self.abuse_type = None
            # TODO: Do something with the user's response
            if selection == 'yes':
                pass
            if selection == 'no':
                pass
            
            return ['Done!']


        return []

    def report_complete(self):
        return self.state == State.REPORT_COMPLETE
    


    

