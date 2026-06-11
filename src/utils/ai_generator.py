import os
import json
from typing import Dict, Any
from src.utils.logger import setup_logger

# Import LangChain core and plugins
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI

logger = setup_logger("ai_generator")

# 1. Role Prompt
ROLE_SYSTEM_PROMPT = """You are an expert Discord Guild Architect. Your job is to design a set of roles for the server based on the user's prompt.
You must output a single, valid JSON object conforming exactly to this structure. Do not output any markdown formatting, backticks, or other text outside the JSON object.

JSON Schema:
{
  "roles": [
    {
      "name": "Management",
      "color": "#e74c3c",
      "hoist": true,
      "mentionable": true,
      "permissions": ["administrator"]
    },
    {
      "name": "Staff",
      "color": "#3498db",
      "hoist": true,
      "mentionable": true,
      "permissions": ["kick_members", "moderate_members"]
    },
    {
      "name": "Verified",
      "color": "#2ecc71",
      "hoist": false,
      "permissions": ["change_nickname", "send_messages"]
    }
  ]
}
"""

# 2. Category Prompt
CATEGORY_SYSTEM_PROMPT = """You are an expert Discord Guild Architect. Your job is to design the categories for the server based on the user's prompt.
Design 4-7 premium categories. Use visual unicode indicators and modern symbols (e.g. 🌟 ENTRANCE, 🎟️ SUPPORT, 🛒 STORE, 💬 COMMUNITY, 👑 STAFF).
You must output a single, valid JSON object conforming exactly to this structure. Do not output any markdown formatting, backticks, or other text outside the JSON object.

JSON Schema:
{
  "categories": [
    "🌟 ENTRANCE",
    "🎟️ SUPPORT",
    "🛒 STORE",
    "💬 COMMUNITY",
    "👑 STAFF"
  ]
}
"""

# 3. Channel Prompt (for a specific category)
CHANNEL_SYSTEM_PROMPT = """You are an expert Discord Guild Architect. Your job is to design the channels for a specific category based on the server theme.
Create 3-8 channels for this category. Use premium channel names with unicode dividers and emojis (e.g. ┃💬・general-chat, ┃📢・announcements, ┃🛒・products).
You must output a single, valid JSON object conforming exactly to this structure. Do not output any markdown formatting, backticks, or other text outside the JSON object.

JSON Schema:
{
  "channels": [
    {
      "name": "┃💬・general-chat",
      "type": "text",
      "topic": "General chat topic",
      "slowmode": 0,
      "nsfw": false,
      "permissions": {}
    }
  ]
}
"""

# 4. Onboarding Prompt (Verification & Tickets & Products)
ONBOARDING_SYSTEM_PROMPT = """You are an expert Discord Guild Architect. Your job is to design the onboarding systems (verification welcome details, ticketing button details, and products list if applicable) based on the server theme.
You must output a single, valid JSON object conforming exactly to this structure. Do not output any markdown formatting, backticks, or other text outside the JSON object.

JSON Schema:
{
  "verification": {
    "enabled": true,
    "channel": "┃👋・welcome",
    "verified_role": "Verified",
    "unverified_role": "Unverified",
    "embed": {
      "title": "Verification Required",
      "description": "Click the verify button to get access.",
      "color": "#2ecc71"
    }
  },
  "tickets": {
    "enabled": true,
    "channel": "┃🎟️・buy",
    "category": "🎟️ SUPPORT",
    "staff_role": "Staff",
    "log_channel": "┃📊・logs",
    "embed": {
      "title": "Support Desk",
      "description": "Click below to open a ticket.",
      "color": "#3498db"
    },
    "types": [
      {
        "name": "Purchase",
        "emoji": "🛒",
        "custom_id": "ticket_purchase"
      }
    ]
  },
  "products": [
    {
      "name": "Product Name",
      "channel_name": "┃🛒・product-name",
      "price": "$10.00",
      "banner_color": "#e74c3c",
      "features": ["Feature 1", "Feature 2"]
    }
  ]
}
"""

class AIGenerator:
    @staticmethod
    async def generate_layout(prompt: str) -> Dict[str, Any]:
        """Generate full server layout step-by-step using LangChain chat models."""
        logger.info("Starting step-by-step layout generation with LangChain...")
        
        # 1. Generate Roles
        logger.info("Generating roles...")
        roles_data = await AIGenerator._query_ai(ROLE_SYSTEM_PROMPT, f"Generate roles for a Discord server themed: {prompt}")
        roles = roles_data.get("roles", [])

        # 2. Generate Categories
        logger.info("Generating categories...")
        cats_data = await AIGenerator._query_ai(CATEGORY_SYSTEM_PROMPT, f"Generate categories for a Discord server themed: {prompt}")
        cat_names = cats_data.get("categories", [])

        # 3. Generate Channels for each Category one by one
        categories = []
        for cat_name in cat_names:
            logger.info(f"Generating channels for category '{cat_name}'...")
            chan_data = await AIGenerator._query_ai(
                CHANNEL_SYSTEM_PROMPT, 
                f"Generate channels for category '{cat_name}' on a server themed: {prompt}"
            )
            channels = chan_data.get("channels", [])
            categories.append({
                "category": cat_name,
                "permissions": {
                    "@everyone": {"view_channel": False},
                    "Verified": {"view_channel": True}
                },
                "channels": channels
            })

        # 4. Generate Onboarding & Products
        logger.info("Generating onboarding, tickets, and products...")
        onboarding_data = await AIGenerator._query_ai(
            ONBOARDING_SYSTEM_PROMPT, 
            f"Generate onboarding, verification, tickets, and products for a server themed: {prompt}"
        )
        
        # Assemble final layout matching original schema
        final_layout = {
            "roles": roles,
            "categories": categories,
            "verification": onboarding_data.get("verification", {}),
            "tickets": onboarding_data.get("tickets", {}),
            "products": onboarding_data.get("products", []),
            "moderation": {
                "automod": {
                    "anti_spam": {"enabled": True},
                    "anti_mention_spam": {"enabled": True, "limit": 5},
                    "anti_invite": {"enabled": True}
                }
            }
        }
        logger.info("Step-by-step layout generation with LangChain completed successfully.")
        return final_layout

    @staticmethod
    def get_llm(json_mode: bool = False):
        """Instantiate correct LangChain LLM based on provider setting."""
        provider = os.getenv("AI_PROVIDER", "gemini").lower()
        
        if provider == "openai":
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY is not set.")
            model_kwargs = {"response_format": {"type": "json_object"}} if json_mode else {}
            return ChatOpenAI(
                model="gpt-4o-mini",
                api_key=api_key,
                temperature=0.7,
                model_kwargs=model_kwargs
            )
            
        elif provider == "kimchi":
            api_key = os.getenv("CASTAI_API_KEY")
            if not api_key:
                raise ValueError("CASTAI_API_KEY is not set.")
            model_kwargs = {"response_format": {"type": "json_object"}} if json_mode else {}
            return ChatOpenAI(
                model="kimi-k2.6",
                api_key=api_key,
                base_url="https://llm.kimchi.dev/openai/v1",
                temperature=0.7,
                model_kwargs=model_kwargs
            )
            
        elif provider == "bluesminds":
            api_key = os.getenv("BLUESMINDS_API_KEY")
            base_url = os.getenv("BLUESMINDS_BASE", "https://api.bluesminds.com/v1")
            model = os.getenv("BLUESMINDS_MODEL", "gpt-5.5")
            if not api_key:
                raise ValueError("BLUESMINDS_API_KEY is not set.")
            model_kwargs = {"response_format": {"type": "json_object"}} if json_mode else {}
            return ChatOpenAI(
                model=model,
                api_key=api_key,
                base_url=base_url,
                temperature=0.7,
                model_kwargs=model_kwargs
            )
            
        else: # Default to Gemini
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise ValueError("GEMINI_API_KEY is not set.")
            os.environ["GOOGLE_API_KEY"] = api_key
            model_kwargs = {"response_mime_type": "application/json"} if json_mode else {}
            return ChatGoogleGenerativeAI(
                model="gemini-2.5-flash",
                temperature=0.7,
                model_kwargs=model_kwargs
            )

    @staticmethod
    async def _query_ai(system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        """Generic AI router using LangChain Chat Models."""
        provider = os.getenv("AI_PROVIDER", "gemini").lower()
        llm = AIGenerator.get_llm(json_mode=True)

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]

        try:
            # Execute asynchronously using LangChain interface
            response = await llm.ainvoke(messages)
            content_text = response.content
            
            cleaned_text = content_text.strip()
            
            # Handle markdown code blocks if present
            if cleaned_text.startswith("```"):
                first_nl = cleaned_text.find("\n")
                if first_nl != -1:
                    cleaned_text = cleaned_text[first_nl:].strip()
                else:
                    cleaned_text = cleaned_text[3:].strip()
                if cleaned_text.endswith("```"):
                    cleaned_text = cleaned_text[:-3].strip()
                    
            try:
                return json.loads(cleaned_text)
            except json.JSONDecodeError as decode_err:
                # Extract first JSON object using brace matching
                first_brace = cleaned_text.find("{")
                if first_brace != -1:
                    depth = 0
                    in_string = False
                    escape = False
                    extracted_text = ""
                    for i in range(first_brace, len(cleaned_text)):
                        char = cleaned_text[i]
                        if escape:
                            escape = False
                            continue
                        if char == '\\':
                            escape = True
                            continue
                        if char == '"':
                            in_string = not in_string
                            continue
                        if not in_string:
                            if char == '{':
                                depth += 1
                            elif char == '}':
                                depth -= 1
                                if depth == 0:
                                    extracted_text = cleaned_text[first_brace:i+1]
                                    break
                    if extracted_text:
                        try:
                            return json.loads(extracted_text)
                        except json.JSONDecodeError:
                            pass
                logger.error(f"Failed to parse LLM JSON. Original: {content_text}")
                raise decode_err
        except Exception as e:
            logger.error(f"Error querying LangChain LLM ({provider}): {e}")
            raise RuntimeError(f"LangChain query failed: {e}")

    @staticmethod
    def get_embeddings():
        """Instantiate correct LangChain Embeddings class based on provider setting."""
        provider = os.getenv("AI_PROVIDER", "gemini").lower()
        
        if provider == "openai":
            from langchain_openai import OpenAIEmbeddings
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY is not set.")
            return OpenAIEmbeddings(api_key=api_key, model="text-embedding-3-small")
            
        elif provider == "kimchi":
            from langchain_openai import OpenAIEmbeddings
            api_key = os.getenv("CASTAI_API_KEY")
            if not api_key:
                raise ValueError("CASTAI_API_KEY is not set.")
            return OpenAIEmbeddings(
                api_key=api_key,
                base_url="https://llm.kimchi.dev/openai/v1",
                model="text-embedding-3-small"
            )
            
        elif provider == "bluesminds":
            # Fall back to Gemini embeddings if available because BluesMinds might not have text-embedding-3-small priced/enabled
            gemini_key = os.getenv("GEMINI_API_KEY")
            if gemini_key:
                try:
                    from langchain_google_genai import GoogleGenerativeAIEmbeddings
                    os.environ["GOOGLE_API_KEY"] = gemini_key
                    return GoogleGenerativeAIEmbeddings(model="models/embedding-001")
                except Exception as gem_err:
                    logger.warning(f"Could not initialize Gemini embeddings as fallback for BluesMinds: {gem_err}")
            
            from langchain_openai import OpenAIEmbeddings
            api_key = os.getenv("BLUESMINDS_API_KEY")
            base_url = os.getenv("BLUESMINDS_BASE", "https://api.bluesminds.com/v1")
            if not api_key:
                raise ValueError("BLUESMINDS_API_KEY is not set.")
            return OpenAIEmbeddings(
                api_key=api_key,
                base_url=base_url,
                model="text-embedding-3-small"
            )
            
        else: # Default to Gemini
            from langchain_google_genai import GoogleGenerativeAIEmbeddings
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise ValueError("GEMINI_API_KEY is not set.")
            os.environ["GOOGLE_API_KEY"] = api_key
            return GoogleGenerativeAIEmbeddings(
                model="models/embedding-001"
            )
