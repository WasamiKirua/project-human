from openai import OpenAI, AsyncOpenAI
from prompts import MEMORY_ANALYSIS_PROMPT
from dotenv import load_dotenv
import os

load_dotenv()

openai_key = os.getenv('OPENAI_API_KEY')

def call_llm(messages):
    client = OpenAI(
        base_url= 'http://localhost:11434/v1',
        api_key='ollama'
    )
    
    response = client.chat.completions.create(
        model="samantha1b",
        messages=messages,
        temperature=0.7
    )
    
    return response.choices[0].message.content

def call_llm_mem(message_text):
    client = OpenAI(api_key=openai_key)
    
    prompt = MEMORY_ANALYSIS_PROMPT.replace('{replacement}', f'{message_text}')

    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "user", "content": f"{prompt}"}
        ]
    )

    return response.choices[0].message

async def call_llm_mem_async(message_text):
    """Async version of call_llm_mem that returns the same object structure"""
    client = AsyncOpenAI(api_key=openai_key)
    
    try:
        prompt = MEMORY_ANALYSIS_PROMPT.replace('{replacement}', f'{message_text}')

        response = await client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "user", "content": f"{prompt}"}
            ]
        )

        return response.choices[0].message
    finally:
        await client.close()

if __name__ == "__main__":
    # Test the LLM call
    messages = [
        #{"role": "system", "content": "You are Samantha an empathic and conscious companion."},
        {"role": "user", "content": "In a few words, what's the meaning of life?"}]
    response = call_llm(messages)
    print(f"Prompt: {messages[0]['content']}")
    print(f"Response: {response}")