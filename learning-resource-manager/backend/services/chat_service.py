from ollama import chat
import os

def send_message(message):
    language_model = os.getenv("LANGUAGE_MODEL")
    response = chat(
            model=language_model,
            messages=[
                {
                    'role':'user',
                    'content': message
                },
            ])
    return respnse.message.content
    
