from openai import OpenAI
import os
import json

token_path = 'tokens.json'
if not os.path.isfile(token_path):
    raise Exception(f"{token_path} not found!")
with open(token_path) as f:
    # If you get an error here, it means your token is formatted incorrectly. Did you put it in quotes?
    tokens = json.load(f)
    openai_token = tokens['OPENAI_API_KEY']

model = 'gpt-4o'

client = OpenAI(api_key = openai_token)