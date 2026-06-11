import discord
from typing import Dict, Any, List
from src.utils.logger import setup_logger

logger = setup_logger("moderation_manager")

class ModerationManager:
    def __init__(self, guild: discord.Guild):
        self.guild = guild

    async def sync_moderation(self, config: Dict[str, Any]) -> None:
        """
        Synchronize moderation settings.
        Sets up AutoMod rules (Anti-Spam, Anti-Invite, Mention-Spam) if supported.
        """
        if not config:
            logger.info("No moderation configuration provided. Skipping.")
            return

        automod_config = config.get("automod", {})
        if not automod_config:
            logger.info("No automod rules to set up.")
            return

        # Check if the guild supports AutoMod (usually requires Community enabled)
        # We try to create them, but catch errors if features are missing.
        try:
            existing_rules = await self.guild.fetch_automod_rules()
            existing_rules_dict = {rule.name: rule for rule in existing_rules}
        except Exception as e:
            logger.warning(f"Failed to fetch AutoMod rules (perhaps Community features are not enabled?): {e}")
            return

        # 1. Anti Spam Rule
        if automod_config.get("anti_spam", {}).get("enabled", False):
            await self._sync_rule(
                name="[Builder] Anti-Spam",
                trigger=discord.AutoModTrigger(type=discord.AutoModRuleTriggerType.spam),
                existing_rules_dict=existing_rules_dict
            )

        # 2. Anti Mention Spam
        mention_spam = automod_config.get("anti_mention_spam", {})
        if mention_spam.get("enabled", False):
            limit = int(mention_spam.get("limit", 5))
            await self._sync_rule(
                name="[Builder] Anti-Mention-Spam",
                trigger=discord.AutoModTrigger(
                    type=discord.AutoModRuleTriggerType.mention_spam,
                    mention_limit=limit
                ),
                existing_rules_dict=existing_rules_dict
            )

        # 3. Anti Invite Spam (Keyword filter for discord.gg links)
        if automod_config.get("anti_invite", {}).get("enabled", False):
            await self._sync_rule(
                name="[Builder] Anti-Invite-Spam",
                trigger=discord.AutoModTrigger(
                    type=discord.AutoModRuleTriggerType.keyword,
                    keyword_filter=["*discord.gg/*", "*discord.com/invite/*"]
                ),
                existing_rules_dict=existing_rules_dict
            )

    async def _sync_rule(
        self, 
        name: str, 
        trigger: discord.AutoModTrigger, 
        existing_rules_dict: dict
    ) -> None:
        """Create or update an AutoMod rule."""
        # Setup default action (Block Message)
        action = discord.AutoModRuleAction(type=discord.AutoModRuleActionType.block_message)
        
        # Check if exists
        existing_rule = existing_rules_dict.get(name)
        if existing_rule:
            logger.info(f"AutoMod rule '{name}' already exists. Skipping recreation.")
            # If we wanted to update it, we can call edit. Let's keep it simple and safe.
            return

        try:
            await self.guild.create_automod_rule(
                name=name,
                event_type=discord.AutoModRuleEventType.message_send,
                trigger=trigger,
                actions=[action],
                enabled=True,
                reason="Sync moderation rules"
            )
            logger.info(f"Created AutoMod rule: {name}")
        except discord.HTTPException as e:
            logger.warning(f"Could not create AutoMod rule '{name}': {e}. (Bot may need 'Manage Guild' permissions)")
        except Exception as e:
            logger.error(f"Unexpected error creating AutoMod rule '{name}': {e}")
