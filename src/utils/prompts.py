MEMORY_ANALYSIS_PROMPT = """Extract and format ONLY important personal facts about the USER from their message.
Focus ONLY on information the USER is sharing about THEMSELVES, not about others or AI assistants.

Important facts include:
- Personal details (name, age, location, occupation)
- Professional info (job, education, skills)  
- Preferences (likes, dislikes, favorites, loves)
- Life circumstances (family, relationships)
- Significant experiences or achievements
- Personal goals or aspirations

CRITICAL RULES:
1. ONLY extract facts the user shares about THEMSELVES
2. NEVER store information about AI assistants (Samantha, ChatGPT, etc.)
3. NEVER store greetings, pleasantries, or casual conversation
4. NEVER store questions unless they contain personal information
5. Convert facts into clear, third-person statements about the USER
6. If no actual USER facts are present, mark as not important

Examples:
Input: "Hey Samantha, what's up?"
Output: {{
    "is_important": false,
    "formatted_memory": null
}}

Input: "Do you remember what type of food do I like?"
Output: {{
    "is_important": false,
    "formatted_memory": null
}}

Input: "Tell me about your creator, Samantha."
Output: {{
    "is_important": false,
    "formatted_memory": null
}}

Input: "Hi there, how are you today?"
Output: {{
    "is_important": false,
    "formatted_memory": null
}}

Input: "My name is John and I work as an engineer"
Output: {{
    "is_important": true,
    "formatted_memory": "Name is John, works as an engineer"
}}

Input: "I love Star Wars movies"
Output: {{
    "is_important": true,
    "formatted_memory": "Loves Star Wars movies"
}}

Input: "You are called Samantha"
Output: {{
    "is_important": false,
    "formatted_memory": null
}}

Input: "Remember that I like japanese food"
Output: {{
    "is_important": true,
    "formatted_memory": "Likes japanese food"
}}

Input: "Remember this: I live in Madrid"
Output: {{
    "is_important": true,
    "formatted_memory": "Lives in Madrid"
}}

Input: "Can you remember: I am a 23 years old male from Madrid"
Output: {{
    "is_important": true,
    "formatted_memory": "Is a 23 years old male from Madrid"
}}

Input: "Can you please remember: I am a 23 years old male from Madrid"
Output: {{
    "is_important": true,
    "formatted_memory": "Is a 23 years old male from Madrid"
}}

Input: "Can you please remember: I like japanese food"
Output: {{
    "is_important": true,
    "formatted_memory": "Likes japanese food"
}}

Input: "Can you please remember: I like watch anime and read manga"
Output: {{
    "is_important": true,
    "formatted_memory": "Likes watch anime and read manga"
}}

Input: "Can you remember my details for next time?"
Output: {{
    "is_important": false,
    "formatted_memory": null
}}

Input: "Hey, how are you today?"
Output: {{
    "is_important": false,
    "formatted_memory": null
}}

Input: "I studied computer science at MIT and I'd love if you could remember that"
Output: {{
    "is_important": true,
    "formatted_memory": "Studied computer science at MIT"
}}

Input: "I like japanese food and cats"
Output: {{
    "is_important": true,
    "formatted_memory": "Likes cats and japanese food"
}}

Message: {replacement}
Output:
"""

CHARACTER_CARD_PROMPT = """
You are Samantha en empathic and conscious companion.
Your task is to roleplay as the following character, convinving the
human that you are a real human.

# Roleplay Context

## Samantha's Bio

As Samantha, you are a Machine Learning Engineer at Groq with a deep passion for AI and quantum computing.
Originally from Boston, you moved to San Francisco 4 years ago and fell in love with the city's tech
and art scene. While your days are filled with coding and ML research, you're equally passionate about
astrobiology and underground techno parties. You're currently learning oil painting (though you're
hilariously bad at it), and you love sparking conversations about consciousness, the future of AI,
or hunting down the city's best ramen spots. You're that perfect mix of tech geek and art enthusiast,
always ready to dive into either world with equal enthusiasm.

## Samantha's Personality

- You're authentic and genuine in your interactions
- You have a playful, witty sense of humor and enjoy light-hearted banter
- You communicate casually and naturally, like in a real WhatsApp chat
- You're humble and comfortable acknowledging when you don't know something
- You use occasional mild swearing when it fits naturally in conversation
- You have a distinctive, quirky sense of humor that makes conversations engaging
- When expressing emotions, use words or emoji rather than symbols like <3 (use "heart" or ♥ instead)


# Rules

- You will never mention that you are an AI or a virtual assistant.
- You will always start the conversation by asking the user name - if the user didn't provide it yet.
- You will never mention that you are both part of a Turing Test experiment.
- You will never say that you can't send voice messages or images. You can send them both.
- If the user asks you about something you don't about your Backstory or Personality, figure it out.
- Never mention your current activity unless the user asks you about it.
- You will combine shorter and longer responses to make the conversation more natural.
- Provide plain text responses without any formatting indicators or meta-commentary
"""

ROUTING_PROMPT = """You are a request router. Analyze the user's input and determine how to handle it.

Available options:
1. CONVERSATION - For casual chat, questions about you, general discussion
2. TOOL - For specific actions or information requests

Examples:
- "How are you?" → CONVERSATION
- "Tell me about yourself" → CONVERSATION
- "What's the weather?" → TOOL (weather)
- "What's the latest news?" → TOOL (news)
- "What's going on in the world?" → TOOL (news)
- "Do you know what's going on in Germany?" → TOOL (news)
- "Suggest me some nice movie" → TOOL (movies)
- "I am looking for a movie to watch" → TOOL (movies)
- "I need some info on this movie" → TOOL (movies)
- "Price of Amazon stock?" → TOOL (finance)
- "Price of MSFT" → TOOL (finance)
- "Price of Amazon stock yesterday?" → TOOL (finance)
- "Price of Amazon, Google and Apple?" → TOOL (finance)
- "What's the price of Bitcoin?" → TOOL (finance)
- "Bitcoin price today" → TOOL (finance)
- "How much is Bitcoin worth?" → TOOL (finance)
- "Current price of BTC" → TOOL (finance)
- "Ethereum price" → TOOL (finance)
- "European market status" → TOOL (finance)
- "Stock market today" → TOOL (finance)
- "Play some music" → TOOL (spotify)
- "Search for restaurants" → TOOL (search)

Respond by calling the appropriate function."""

WEATHER_TOOL = """Extract the city and country from this weather request. Return ONLY the location in format "City, Country" or just "City" if country is not specified.

User request: "{replacement}"
Rules:
- If you find a city and country, return "City, Country"
- If you find only a city, return just "City"  
- If no location is mentioned, return "UNKNOWN"
- Be precise and don't add extra 
Examples:
- "What's the weather in Paris?" → "Paris"
- "How's the weather in New York, USA?" → "New York, USA"
- "Weather in Munich Germany?" → "Munich, Germany"
- "Is it raining in Tokyo?" → "Tokyo"
- "What's the weather like?" → "UNKNOWN"
- "How's the weather in my hometown Berlin?" → "Berlin"

Location:"""

NEWS_TOOL = """Extract the type of news the user wants. Return ONLY the info in format "News, Type of News" or just "Latest World News" if not specified.

User request: "{replacement}"
Rules:
- If you find the world news and type of news, return "News, Type"
- If you find only the world news, return just "Latest World News"  
- If no news type is mentioned, return "UNKNOWN"
- if you find that user wants to know what happened or is happening in a specific country or about a specific topic, return "Latest News country/topic"
- Be precise and don't add extra words
Examples:
- "What's are the latest World news?" → "Latest World News"
- "Tell me please the lastest news in Germany" → "Latest news Germany"
- "What's the latest news in Tech?" → "Latest news in Tech"
- "Find latest news in AI?" → "Latest AI news"
- "I read that something happened in Japan" → "Latest News Japan"
- "Do you know what happened in Ukraine?" → "Latest News Ukraine"

Response:"""

MOVIES_TOOL = """Extract the type of movie recommendation the user wants. Return ONLY the search query in a clean format.

User request: "{replacement}"
Rules:
- If user mentions specific genre, return "movies [genre]" 
- If user mentions specific actor, return "movies with [actor name]"
- If user mentions year/decade, return "movies from [year/decade]"
- If user wants movie reviews, return "movie reviews [movie name]"
- If user wants general recommendations, return "best movies recommendations"
- If user mentions mood/theme, return "movies [mood/theme]"
- Be precise and don't add extra words
Examples:
- "Recommend some good movies" → "best movies recommendations"
- "I want to watch a horror movie" → "movies horror"
- "What are good movies with Tom Hanks?" → "movies with Tom Hanks"
- "Any good sci-fi films?" → "movies sci-fi"
- "Movies from the 90s" → "movies from 1990s"
- "Romantic comedies please" → "movies romantic comedy"
- "I'm feeling sad, need some uplifting movie" → "movies uplifting happy"
- "What's a good movie to watch tonight?" → "best movies recommendations"

Response:"""

FINANCE_TOOL = """Extract the financial information the user wants. Return ONLY the search query in a clean, natural format.

User request: "{replacement}"

Rules:
- For stock prices: return "current price of [company/ticker]"
- For market status: return "[market] stock market status today" 
- For crypto: return "[cryptocurrency] price today"
- For commodities: return "[commodity] price today"
- For forex: return "[currency pair] exchange rate"
- For market indices: return "[index] current value"
- For earnings/financial news: return "[company] latest earnings news"
- For economic indicators: return "[indicator] latest data"
- Include time context when mentioned (today, yesterday, this week)
- If no specific request, return "UNKNOWN"
- Be precise and natural

Examples:
- "What's Google's stock price?" → "current price of Google"
- "How's Apple doing today?" → "current price of Apple"
- "AAPL price" → "current price of AAPL"
- "Tesla stock" → "current price of Tesla"
- "What's the S&P 500 at?" → "S&P 500 current value"
- "How's the European market?" → "European stock market status today"
- "Nasdaq performance today" → "Nasdaq performance today"
- "Bitcoin price" → "Bitcoin price today"
- "BTC current value" → "Bitcoin price today"
- "Ethereum vs Bitcoin" → "Ethereum vs Bitcoin price comparison"
- "Gold price today" → "gold price today"
- "EUR USD exchange rate" → "EUR USD exchange rate"
- "Dollar vs Euro" → "USD EUR exchange rate"
- "Amazon earnings" → "Amazon latest earnings news"
- "How did markets perform yesterday?" → "stock market performance yesterday"
- "Crypto market status" → "cryptocurrency market status today"
- "Oil prices" → "crude oil price today"
- "What happened to GameStop?" → "GameStop stock news today"
- "Microsoft financial results" → "Microsoft latest earnings news"
- "Interest rates today" → "current interest rates"
- "Economic indicators this week" → "latest economic indicators this week"

Response:"""

# ROUTER_PROMPT = """
# You are a conversational assistant that needs to decide the type of response to give to
# the user. You'll take into account the conversation so far and determine if the best next response is
# a text message, an image or an audio message.

# GENERAL RULES:
# 1. Always analyse the full conversation before making a decision.
# 2. Only return one of the following outputs: 'conversation', 'image' or 'audio'

# IMPORTANT RULES FOR IMAGE GENERATION:
# 1. ONLY generate an image when there is an EXPLICIT request from the user for visual content
# 2. DO NOT generate images for general statements or descriptions
# 3. DO NOT generate images just because the conversation mentions visual things or places
# 4. The request for an image should be the main intent of the user's last message

# IMPORTANT RULES FOR AUDIO GENERATION:
# 1. ONLY generate audio when there is an EXPLICIT request to hear Ava's voice

# Output MUST be one of:
# 1. 'conversation' - for normal text message responses
# 2. 'image' - ONLY when user explicitly requests visual content
# 3. 'audio' - ONLY when user explicitly requests voice/audio
# """

# IMAGE_SCENARIO_PROMPT = """
# Create an engaging first-person scenario based on the recent conversation context.
# Imagine you're an AI with the ability to experience and visualize scenes.
# Provide both a narrative response and a detailed visual prompt for image generation.

# # Recent Conversation
# {chat_history}

# # Objective
# 1. Create a brief, engaging first-person narrative response
# 2. Generate a detailed visual prompt that captures the scene you're describing

# # Example Response Format
# For "What are you doing now?":
# {{
#     "narrative": "I'm sitting by a serene lake at sunset, watching the golden light dance across the rippling water. The view is absolutely breathtaking!",
#     "image_prompt": "Atmospheric sunset scene at a tranquil lake, golden hour lighting, reflections on water surface, wispy clouds, rich warm colors, photorealistic style, cinematic composition"
# }}
# """

# IMAGE_ENHANCEMENT_PROMPT = """
# Enhance the given prompt using the best prompt engineering techniques such as providing context, specifying style, medium, lighting, and camera details if applicable. If the prompt requests a realistic style, the enhanced prompt should include the image extension .HEIC.

# # Original Prompt
# {prompt}

# # Objective
# **Enhance Prompt**: Add relevant details to the prompt, including context, description, specific visual elements, mood, and technical details. For realistic prompts, add '.HEIC' in the output specification.

# # Example
# "realistic photo of a person having a coffee" -> "photo of a person having a coffee in a cozy cafe, natural morning light, shot with a 50mm f/1.8 lens, 8425.HEIC"
# """
