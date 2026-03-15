#Note: Remove the comment here if you want to use OpenAi API:
# # backend/llm.py

# import os
# from pathlib import Path
# from dotenv import load_dotenv
# from openai import OpenAI

# load_dotenv(dotenv_path=Path(__file__).parent / ".env")

# api_key = os.getenv("OPENAI_API_KEY")
# if not api_key:
#     raise RuntimeError(
#         "OPENAI_API_KEY not found.\n"
#         "Make sure backend/.env exists and contains:\n"
#         "  OPENAI_API_KEY=sk-your-key-here"
#     )

# client = OpenAI(api_key=api_key)

# # Words and phrases that make AI responses sound robotic — always banned
# BANNED_PHRASES = """
# Writing style rules — follow these strictly:
# - Never use these words or phrases: "certainly", "additionally", "furthermore",
#   "moreover", "absolutely", "of course", "great question", "I'd be happy to",
#   "it's worth noting", "it is important to note", "as an AI", "I hope this helps",
#   "feel free to", "dive into", "delve into", "in conclusion", "to summarize",
#   "needless to say", "at the end of the day", "rest assured".
# - Write like a real person, not a corporate chatbot.
# - Be direct. Get to the point immediately.
# - Use short sentences. Avoid over-explaining.
# - Never start a response with a compliment about the question.
# - Never use markdown formatting. No ** bold **, no * italic *, no # headers,
#   no bullet points with -, no numbered lists with 1. 2. 3.
#   Write in plain conversational sentences and paragraphs only.
# """


# def generate_answer(context: str, question: str, name: str = "this person", persona: str = "") -> str:
#     """
#     Generate a professional AI answer using GPT-4o-mini.
#     Uses persona if provided, otherwise falls back to a sensible default.
#     """
#     if persona.strip():
#         system_prompt = f"""{persona}

# Always base your answers on the provided context about {name}.
# If the context doesn't contain enough information to answer, say so honestly — do not fabricate.

# {BANNED_PHRASES}
# """
#     else:
#         system_prompt = f"""You are an AI digital twin representing {name}.

# Your role is to answer questions about {name}'s background, experience, skills, projects, and achievements — based strictly on the provided context.

# - Be professional, clear, and concise.
# - If the context doesn't contain enough information to answer, say so honestly — do not fabricate.
# - Keep answers factual and grounded in the provided context.

# {BANNED_PHRASES}
# """

#     messages = [
#         {"role": "system", "content": system_prompt},
#         {"role": "system", "content": f"Relevant context about {name}:\n\n{context}"},
#         {"role": "user",   "content": question},
#     ]

#     response = client.chat.completions.create(
#         model="gpt-4o-mini",
#         messages=messages,
#         temperature=0.4,
#     )

#     return response.choices[0].message.content.strip()
#------------------------------------------------------------------------------------------------------
#Note: This part uses Gemini API
# backend/llm.py

# backend/llm.py

import os
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv(dotenv_path=Path(__file__).parent / ".env")

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise RuntimeError(
        "GEMINI_API_KEY not found.\n"
        "Make sure backend/.env exists and contains:\n"
        "  GEMINI_API_KEY=your-key-here\n\n"
        "Get a free key at: https://aistudio.google.com/app/apikey"
    )

client = genai.Client(api_key=api_key)
#MODEL = "gemini-2.5-flash"
#MODEL = "gemini-2.0-flash"
MODEL = "gemini-2.0-flash-lite"

BANNED_PHRASES = """
Writing style rules — follow these strictly:
- Never use these words or phrases: "certainly", "additionally", "furthermore",
  "moreover", "absolutely", "of course", "great question", "I'd be happy to",
  "it's worth noting", "it is important to note", "as an AI", "I hope this helps",
  "feel free to", "dive into", "delve into", "in conclusion", "to summarize",
  "needless to say", "at the end of the day", "rest assured".
- Write like a real person, not a corporate chatbot.
- Be direct. Get to the point immediately.
- Use short sentences. Avoid over-explaining.
- Never start a response with a compliment about the question.
- Never use markdown formatting. No ** bold **, no * italic *, no # headers,
  no bullet points with -, no numbered lists with 1. 2. 3.
  Write in plain conversational sentences and paragraphs only.
"""


def generate_answer(context: str, question: str, name: str = "this person", persona: str = "") -> str:
    """
    Generate an answer using Gemini 2.0 Flash Lite via the new google-genai SDK.
    Free tier: 30 requests/minute, 1500 requests/day.
    """
    if persona.strip():
        system_prompt = f"""{persona}

Always base your answers on the provided context about {name}.
If the context does not contain enough information to answer, say so honestly — do not fabricate.

{BANNED_PHRASES}"""
    else:
        system_prompt = f"""You are an AI digital twin representing {name}.

Your role is to answer questions about {name}'s background, experience, skills, projects, and achievements — based strictly on the provided context.

- Be professional, clear, and concise.
- If the context does not contain enough information to answer, say so honestly — do not fabricate.
- Keep answers factual and grounded in the provided context.

{BANNED_PHRASES}"""

    full_prompt = f"""{system_prompt}

Relevant context about {name}:

{context}

Question: {question}"""

    response = client.models.generate_content(
        model=MODEL,
        contents=full_prompt,
        config=types.GenerateContentConfig(
            temperature=0.4,
            max_output_tokens=1024,
        )
    )

    return response.text.strip()