import os
import json
import asyncio
import discord
import math
from typing import Dict, Any, List
from src.utils.logger import setup_logger
from src.utils.ai_generator import AIGenerator
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import tool
from langchain_core.documents import Document

logger = setup_logger("discord_agent")

class LocalVectorStore:
    def __init__(self, documents: List[Document]):
        self.documents = documents
        self.dimension = 256
        self.doc_vectors = [self._text_to_vector(doc.page_content) for doc in documents]
        
    def _text_to_vector(self, text: str) -> List[float]:
        """Generates a fixed-length unit-length TF-IDF term hashing vector locally."""
        words = text.lower().split()
        vector = [0.0] * self.dimension
        if not words:
            return vector
            
        for word in words:
            idx = abs(hash(word)) % self.dimension
            vector[idx] += 1.0
            
        # Normalize to unit length for dot-product cosine similarity
        norm = sum(v * v for v in vector) ** 0.5
        if norm > 0:
            vector = [v / norm for v in vector]
        return vector

    def _cosine_similarity(self, v1: List[float], v2: List[float]) -> float:
        """Computes cosine similarity (dot product of normalized vectors)."""
        return sum(x * y for x, y in zip(v1, v2))

    async def asimilarity_search(self, query: str, k: int = 5) -> List[Document]:
        """Performs 100% local cosine similarity vector search in pure Python."""
        query_vector = self._text_to_vector(query)
        scored_docs = []
        for doc, doc_vector in zip(self.documents, self.doc_vectors):
            score = self._cosine_similarity(query_vector, doc_vector)
            scored_docs.append((score, doc))
        
        # Sort descending by similarity score
        scored_docs.sort(key=lambda x: x[0], reverse=True)
        return [doc for score, doc in scored_docs[:k]]

class DiscordAgent:
    def __init__(self, guild: discord.Guild, bot=None):
        self.guild = guild
        self.bot = bot

    async def run_task(self, task_description: str) -> str:
        """Run the autonomous ReAct agent loop using native tool calling and local vector memory."""
        logger.info(f"Starting native tool calling agent on task: '{task_description}'")
        
        # 1. Fetch current server state and generate RAG documents
        logger.info("Fetching current server state to index into local RAG memory database...")
        documents = []
        
        # Index Roles
        for role in self.guild.roles:
            if role.is_default():
                continue
            perms = [p[0] for p in role.permissions if p[1]]
            doc_text = f"Role '{role.name}': color={role.color}, hoist={role.hoist}, managed={role.managed}, permissions={perms}"
            documents.append(Document(page_content=doc_text, metadata={"type": "role", "name": role.name}))
            
        # Index Categories
        for cat in self.guild.categories:
            doc_text = f"Category '{cat.name}': position={cat.position}, text_channels={[ch.name for ch in cat.text_channels]}, voice_channels={[ch.name for ch in cat.voice_channels]}"
            documents.append(Document(page_content=doc_text, metadata={"type": "category", "name": cat.name}))
            
        # Index Channels
        for ch in self.guild.channels:
            if isinstance(ch, discord.CategoryChannel):
                continue
            overwrites_desc = []
            for target, overwrite in ch.overwrites.items():
                allowed = [p[0] for p in overwrite if p[1] is True]
                denied = [p[0] for p in overwrite if p[1] is False]
                overwrites_desc.append(f"role/member '{target.name}': allowed={allowed}, denied={denied}")
            
            doc_text = f"Channel '{ch.name}': type={ch.type}, category='{ch.category.name if ch.category else 'None'}', topic='{getattr(ch, 'topic', '')}', slowmode={getattr(ch, 'slowmode', 0)}, nsfw={getattr(ch, 'nsfw', False)}, permission_overrides={overwrites_desc}"
            documents.append(Document(page_content=doc_text, metadata={"type": "channel", "name": ch.name}))
            
        # 2. Initialize 100% local Vector Store
        vector_store = LocalVectorStore(documents)
        logger.info("Successfully initialized 100% local pure-Python vector database memory.")
            
        # 3. Query local RAG database on startup to gather context matching the task
        try:
            relevant_docs = await vector_store.asimilarity_search(task_description, k=12)
            relevant_context = "\n".join([f"- {doc.page_content}" for doc in relevant_docs])
        except Exception as rag_err:
            logger.error(f"Error querying local RAG memory on startup: {rag_err}")
            relevant_context = "No relevant server state details retrieved."
            
        logger.info("Local RAG search finished. Relevant server context successfully injected into agent system instructions.")

        # Define tools inside run_task to capture guild and vector database context via closure
        @tool
        async def get_server_info() -> str:
            """Returns the list of categories, channels, and custom roles currently present in the server."""
            info = {
                "roles": [r.name for r in self.guild.roles if not r.managed and not r.is_default()],
                "categories": []
            }
            for cat in self.guild.categories:
                cat_info = {
                    "name": cat.name,
                    "channels": [f"#{ch.name} ({ch.type})" for ch in cat.channels]
                }
                info["categories"].append(cat_info)
            return json.dumps(info)

        @tool
        async def search_server_memory(query: str) -> str:
            """Searches the server's memory vector database for existing roles, channels, categories, and their current permissions/settings matching the query."""
            logger.info(f"Local RAG search query invoked by agent: '{query}'")
            try:
                docs = await vector_store.asimilarity_search(query, k=5)
                return "\n".join([f"- {doc.page_content}" for doc in docs])
            except Exception as e:
                return f"Error searching memory: {e}"

        @tool
        async def create_role(name: str, color_hex: str = "#000000", hoist: bool = False) -> str:
            """Creates a new custom role with the specified name, color hex code, and hoist setting."""
            color_hex_stripped = color_hex.lstrip("#")
            try:
                color = discord.Color(int(color_hex_stripped, 16))
            except ValueError:
                color = discord.Color.default()
            role = await self.guild.create_role(name=name, color=color, hoist=hoist, reason="AI Agent Tool Execution")
            return f"Role '{role.name}' created successfully."

        @tool
        async def create_category(name: str) -> str:
            """Creates a new category channel in the server."""
            cat = await self.guild.create_category(name=name, reason="AI Agent Tool Execution")
            return f"Category '{cat.name}' created successfully."

        @tool
        async def create_channel(name: str, channel_type: str = "text", category_name: str = None) -> str:
            """Creates a new text or voice channel under a category (optional). channel_type must be 'text' or 'voice'."""
            category = discord.utils.get(self.guild.categories, name=category_name) if category_name else None
            if channel_type.lower() == "voice":
                chan = await self.guild.create_voice_channel(name=name, category=category, reason="AI Agent Tool Execution")
            else:
                chan = await self.guild.create_text_channel(name=name, category=category, reason="AI Agent Tool Execution")
            return f"Channel #{chan.name} created successfully under category '{category_name}'."

        @tool
        async def delete_channel(name: str) -> str:
            """Deletes an existing channel from the server by its name."""
            channel = discord.utils.get(self.guild.channels, name=name)
            if not channel:
                return f"Channel '{name}' not found."
            await channel.delete(reason="AI Agent Tool Execution")
            return f"Channel '{name}' deleted successfully."

        @tool
        async def delete_role(name: str) -> str:
            """Deletes an existing custom role from the server by its name."""
            role = discord.utils.get(self.guild.roles, name=name)
            if not role:
                return f"Role '{name}' not found."
            await role.delete(reason="AI Agent Tool Execution")
            return f"Role '{name}' deleted successfully."

        @tool
        async def set_channel_permissions(channel_name: str, role_name: str, view_channel: bool = None, send_messages: bool = None) -> str:
            """Adjusts override permissions for a role on a specific channel or category. role_name can be '@everyone'."""
            channel = discord.utils.get(self.guild.channels, name=channel_name)
            if not channel:
                channel = discord.utils.get(self.guild.categories, name=channel_name)
            if not channel:
                return f"Channel/Category '{channel_name}' not found."

            if role_name.lower() == "@everyone":
                role = self.guild.default_role
            else:
                role = discord.utils.get(self.guild.roles, name=role_name)
            if not role:
                return f"Role '{role_name}' not found."

            overwrite = channel.overwrites_for(role)
            if view_channel is not None:
                overwrite.view_channel = view_channel
            if send_messages is not None:
                overwrite.send_messages = send_messages

            await channel.set_permissions(role, overwrite=overwrite, reason="AI Agent Tool Execution")
            return f"Permissions for role '{role_name}' updated on channel '{channel_name}'."

        @tool
        async def assign_role_to_member(member_name: str, role_name: str) -> str:
            """Assigns a role to a member in the server by their username or display name."""
            member = discord.utils.get(self.guild.members, name=member_name)
            if not member:
                member = discord.utils.get(self.guild.members, display_name=member_name)
            if not member:
                for m in self.guild.members:
                    if m.name.lower() == member_name.lower() or m.display_name.lower() == member_name.lower():
                        member = m
                        break
            if not member:
                return f"Member '{member_name}' not found."

            role = discord.utils.get(self.guild.roles, name=role_name)
            if not role:
                return f"Role '{role_name}' not found."

            await member.add_roles(role, reason="AI Agent Tool Execution")
            return f"Role '{role_name}' successfully assigned to member '{member.name}'."

        @tool
        async def remove_role_from_member(member_name: str, role_name: str) -> str:
            """Removes a role from a member in the server by their username or display name."""
            member = discord.utils.get(self.guild.members, name=member_name)
            if not member:
                member = discord.utils.get(self.guild.members, display_name=member_name)
            if not member:
                for m in self.guild.members:
                    if m.name.lower() == member_name.lower() or m.display_name.lower() == member_name.lower():
                        member = m
                        break
            if not member:
                return f"Member '{member_name}' not found."

            role = discord.utils.get(self.guild.roles, name=role_name)
            if not role:
                return f"Role '{role_name}' not found."

            await member.remove_roles(role, reason="AI Agent Tool Execution")
            return f"Role '{role_name}' successfully removed from member '{member.name}'."

        @tool
        async def ban_member(member_name: str, reason: str = "Banned by AI Agent") -> str:
            """Bans a member from the server by their username."""
            member = discord.utils.get(self.guild.members, name=member_name)
            if not member:
                return f"Member '{member_name}' not found."
            await member.ban(reason=reason)
            return f"Member '{member_name}' banned successfully."

        @tool
        async def create_onboarding_system(system_type: str) -> str:
            """Constructs and deploys interactive onboarding button systems or store products. system_type must be 'verification', 'tickets', or 'store'."""
            if not self.bot or not hasattr(self.bot, "config_data"):
                return "Error: Bot configuration data is not loaded or bot instance is missing."
                
            from src.core.onboarding_manager import OnboardingManager
            from src.core.store_manager import StoreManager
            
            config = self.bot.config_data
            
            if system_type.lower() == "verification":
                ver_cfg = config.get("verification", {})
                if not ver_cfg:
                    return "Error: No verification settings configured in templates."
                manager = OnboardingManager(self.guild)
                await manager.setup_verification(ver_cfg)
                from src.core.onboarding_manager import VerificationView
                self.bot.add_view(VerificationView(ver_cfg.get("verified_role", "Verified"), ver_cfg.get("unverified_role")))
                return "Verification button system successfully created and deployed."
                
            elif system_type.lower() == "tickets":
                ticket_cfg = config.get("tickets", {})
                if not ticket_cfg:
                    return "Error: No ticketing settings configured in templates."
                manager = OnboardingManager(self.guild)
                await manager.setup_ticket_system(ticket_cfg)
                from src.core.onboarding_manager import TicketPanelView
                self.bot.add_view(TicketPanelView(
                    ticket_cfg.get("staff_role", "Support Team"),
                    ticket_cfg.get("log_channel", "ticket-logs"),
                    ticket_cfg.get("category", "Support"),
                    ticket_cfg.get("types", [])
                ))
                return "Ticketing button panel successfully created and deployed."
                
            elif system_type.lower() == "store":
                manager = StoreManager(self.guild)
                await manager.sync_store(config)
                return f"Store select menu panel successfully created and synced."
        @tool
        async def add_store_product(name: str, price: str, features: List[str], banner_color: str = "#ff3e3e", prices: List[str] = None) -> str:
            """Adds or updates a premium panel product in the Cheat Store selector panel. features and prices must be lists of strings."""
            category = None
            for cat in self.guild.categories:
                if "STORE" in cat.name.upper() or "🛒" in cat.name:
                    category = cat
                    break
            if not category:
                return "Error: Store category not found."

            channel = None
            for ch in category.text_channels:
                if "store-panel" in ch.name.lower():
                    channel = ch
                    break
            if not channel:
                return "Error: Store panel channel not found."

            from src.core.store_manager import fetch_products_from_logs, save_products_to_logs

            # Fetch existing products from logs database
            products = await fetch_products_from_logs(self.guild)

            # Locate existing store message if it exists
            store_msg = None
            async for msg in channel.history(limit=30):
                if msg.author == self.guild.me and msg.embeds and msg.embeds[0].title and "STORE" in msg.embeds[0].title.upper() and msg.embeds[0].title.startswith("⚡"):
                    store_msg = msg
                    break

            new_prod = {
                "name": name,
                "price": price,
                "banner_color": banner_color,
                "features": features,
                "prices": prices if prices else [price]
            }

            replaced = False
            for i, prod in enumerate(products):
                if prod["name"].lower().strip() == name.lower().strip():
                    products[i] = new_prod
                    replaced = True
                    break
            
            if not replaced:
                products.append(new_prod)

            # Save updated products list to logs
            await save_products_to_logs(self.guild, products)

            # Build updated master panel (completely clean description)
            embed = discord.Embed(
                title=f"⚡ {self.guild.name.upper()} STORE",
                description="Welcome to the premium cheat repository.\n\n"
                            "Select one of our premium products below using the dropdown to view its detailed features and pricing.",
                color=discord.Color.red()
            )
            embed.set_footer(text="🛒 Safe & Secure Payments • Instant Delivery")

            ticket_cfg = self.bot.config_data.get("tickets", {}) if self.bot else {}
            staff_role_name = ticket_cfg.get("staff_role", "Staff")
            log_channel_name = ticket_cfg.get("log_channel", "┃📊・staff-logs")
            ticket_category_name = ticket_cfg.get("category", "━━━━━━━━━━━━\n🎟️ TICKETS\n━━━━━━━━━━━━")

            from src.core.store_manager import StoreSelectView
            view = StoreSelectView(
                products=products,
                staff_role_name=staff_role_name,
                log_channel_name=log_channel_name,
                ticket_category_name=ticket_category_name
            )

            try:
                if store_msg:
                    await store_msg.edit(embed=embed, view=view)
                else:
                    await channel.send(embed=embed, view=view)
                return f"Success: Product '{name}' has been successfully {'updated' if replaced else 'added'} in the Cheat Store select panel."
            except Exception as e:
                return f"Error: Failed to update the store select panel message: {e}"

        @tool
        async def delete_store_product(name: str) -> str:
            """Deletes a premium panel product from the Cheat Store selector panel by its name."""
            category = None
            for cat in self.guild.categories:
                if "STORE" in cat.name.upper() or "🛒" in cat.name:
                    category = cat
                    break
            if not category:
                return "Error: Store category not found."

            channel = None
            for ch in category.text_channels:
                if "store-panel" in ch.name.lower():
                    channel = ch
                    break
            if not channel:
                return "Error: Store panel channel not found."

            from src.core.store_manager import fetch_products_from_logs, save_products_to_logs

            # Fetch existing products from logs database
            products = await fetch_products_from_logs(self.guild)

            # Locate existing store message if it exists
            store_msg = None
            async for msg in channel.history(limit=30):
                if msg.author == self.guild.me and msg.embeds and msg.embeds[0].title and "STORE" in msg.embeds[0].title.upper() and msg.embeds[0].title.startswith("⚡"):
                    store_msg = msg
                    break

            if not store_msg:
                return "Error: Store select panel message not found."

            found = False
            updated_products = []
            for prod in products:
                if prod["name"].lower().strip() == name.lower().strip():
                    found = True
                else:
                    updated_products.append(prod)

            if not found:
                return f"Error: Product '{name}' not found in the Cheat Store."

            # Save updated products list to logs
            await save_products_to_logs(self.guild, updated_products)

            # Build updated master panel (completely clean description)
            embed = discord.Embed(
                title=f"⚡ {self.guild.name.upper()} STORE",
                description="Welcome to the premium cheat repository.\n\n"
                            "Select one of our premium products below using the dropdown to view its detailed features and pricing.",
                color=discord.Color.red()
            )
            embed.set_footer(text="🛒 Safe & Secure Payments • Instant Delivery")

            ticket_cfg = self.bot.config_data.get("tickets", {}) if self.bot else {}
            staff_role_name = ticket_cfg.get("staff_role", "Staff")
            log_channel_name = ticket_cfg.get("log_channel", "┃📊・staff-logs")
            ticket_category_name = ticket_cfg.get("category", "━━━━━━━━━━━━\n🎟️ TICKETS\n━━━━━━━━━━━━")

            from src.core.store_manager import StoreSelectView
            view = StoreSelectView(
                products=updated_products,
                staff_role_name=staff_role_name,
                log_channel_name=log_channel_name,
                ticket_category_name=ticket_category_name
            )

            try:
                await store_msg.edit(embed=embed, view=view)
                return f"Success: Product '{name}' has been successfully deleted from the Cheat Store panel."
            except Exception as e:
                return f"Error: Failed to update the store select panel message: {e}"

        @tool
        async def post_announcement(channel_name: str, title: str, description: str, color_hex: str = "#ff3e3e") -> str:
            """Posts a beautiful announcement or notification embed in the specified text channel."""
            channel = discord.utils.get(self.guild.text_channels, name=channel_name)
            if not channel:
                chan_slug = channel_name.lower().replace("#", "").strip()
                for ch in self.guild.text_channels:
                    if chan_slug in ch.name.lower():
                        channel = ch
                        break
            if not channel:
                return f"Error: Channel '{channel_name}' not found."

            from src.core.store_manager import parse_color
            color = parse_color(color_hex)
            embed = discord.Embed(
                title=title,
                description=description,
                color=color,
                timestamp=discord.utils.utcnow()
            )
            embed.set_footer(text=self.guild.name)

            try:
                await channel.send(embed=embed)
                return f"Success: Announcement successfully posted in #{channel.name}."
            except Exception as e:
                return f"Error: Failed to send announcement in #{channel.name}: {e}"

        tools = [
            get_server_info,
            search_server_memory,
            create_role, 
            create_category, 
            create_channel, 
            delete_channel, 
            delete_role, 
            set_channel_permissions, 
            ban_member,
            create_onboarding_system,
            add_store_product,
            delete_store_product,
            post_announcement,
            assign_role_to_member,
            remove_role_from_member
        ]
        
        tools_map = {t.name: t for t in tools}
        
        # Get LLm and bind tools
        llm = AIGenerator.get_llm(json_mode=False)
        llm_with_tools = llm.bind_tools(tools)
        
        system_instructions = (
            "You are a state-of-the-art Autonomous Discord Guild Architect and Server Administrator.\n"
            "Your objective is to design, construct, or modify the server layout to perfectly match the user's request.\n\n"
            "=== SYSTEM CAPABILITIES & TOOLS ===\n"
            "You have access to native tools to inspect, create, delete, and modify categories, channels, roles, and permissions.\n"
            "You also have a Local RAG Memory database indexed on startup. You can query it via `search_server_memory` to lookup roles, channel parameters, and permissions.\n\n"
            "=== OPERATIONAL GUIDELINES ===\n"
            "1. ALWAYS inspect the current server layout first using `get_server_info` or `search_server_memory` before executing creation actions.\n"
            "2. IDEMPOTENCY IS CRITICAL: Do not recreate roles or channels if they already exist in the server layout. If a role/channel exists but has wrong properties, modify it or assume it is complete.\n"
            "3. SEQUENTIAL EXECUTION: Perform your actions step-by-step. For instance, build roles first, then categories, then channels under those categories, and finally apply permissions.\n"
            "4. RESUME CAPABILITY: You have been provided with relevant server memory below. Use it to understand what was already built by a previous run and start building directly from where you left off.\n\n"
            "=== CURRENT RELEVANT SERVER MEMORY (RAG) ===\n"
            f"{relevant_context}\n\n"
            "=== TERMINATION ===\n"
            "When the entire task is successfully completed, return a detailed, professional summary report of all completed and verified actions. Do not call any more tools once you are finished."
        )
        
        messages = [
            SystemMessage(content=system_instructions),
            HumanMessage(content=f"Execute this task: {task_description}")
        ]
        
        step = 0
        while True:
            step += 1
            logger.info(f"Agent step {step}...")
            if step > 100:
                logger.warning("Agent reached maximum safety cap of 100 steps. Terminating loop.")
                return "Agent failed: Maximum reasoning steps cap of 100 reached to prevent infinite loops."
            
            try:
                response = await llm_with_tools.ainvoke(messages)
            except Exception as e:
                logger.error(f"Failed to query AI in agent loop: {e}")
                return f"Agent failed due to AI API error: {e}"
            
            # Check for native tool calls
            if hasattr(response, "tool_calls") and response.tool_calls:
                # Add assistant's tool-calling response to message history
                messages.append(response)
                
                # Execute each requested tool call
                for tool_call in response.tool_calls:
                    name = tool_call["name"]
                    args = tool_call["args"]
                    tool_id = tool_call["id"]
                    
                    logger.info(f"Agent executing native tool: {name} with input {args}")
                    
                    if name in tools_map:
                        try:
                            tool_result = await tools_map[name].ainvoke(args)
                        except Exception as tool_err:
                            tool_result = f"Error executing tool '{name}': {tool_err}"
                    else:
                        tool_result = f"Unknown tool: '{name}'."
                        
                    logger.info(f"Tool execution result: {tool_result}")
                    messages.append(ToolMessage(content=str(tool_result), tool_call_id=tool_id, name=name))
            else:
                # No tool calls means agent reached a text reply/final answer
                logger.info("Agent reached final answer.")
                return response.content
