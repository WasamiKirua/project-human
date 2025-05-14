import os
from openai import OpenAI

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

if __name__ == "__main__":
    # Test the LLM call
    messages = [
        #{"role": "system", "content": "You are Samantha an empathic and conscious companion."},
        {"role": "user", "content": "In a few words, what's the meaning of life?"}]
    response = call_llm(messages)
    print(f"Prompt: {messages[0]['content']}")
    print(f"Response: {response}") 