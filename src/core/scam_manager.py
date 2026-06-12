import os
import json
import base64
import hashlib
import re
import httpx
import discord
from typing import Dict, Any, List, Optional, Tuple
from src.utils.logger import setup_logger

logger = setup_logger("scam_manager")

class ScamManager:
    def __init__(self):
        self.config_path = r"c:\Users\Firda\Documents\Serverbuilder\src\config\scam_config.json"
        self.config = {
            "risk_thresholds": {
                "delete": 40,
                "warn": 60,
                "timeout": 80,
                "alert": 95
            },
            "auto_delete": True,
            "auto_timeout": True,
            "alert_channel": "scam-alerts"
        }
        self.load_config()
        
        # In-memory caches and logs
        self.image_cache: Dict[str, Dict[str, Any]] = {}  # sha256 -> {"score": int, "reasons": list, "text": str}
        self.history: List[Dict[str, Any]] = []           # list of recent scam detection events
        self.stats = {
            "messages_scanned": 0,
            "images_scanned": 0,
            "scams_found": 0,
            "users_flagged": set()  # set of user IDs
        }

    def load_config(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    self.config = json.load(f)
                logger.info("Scam Shield configuration loaded successfully.")
            except Exception as e:
                logger.error(f"Failed to load Scam Shield config: {e}")

    def save_config(self):
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4)
            logger.info("Scam Shield configuration saved.")
        except Exception as e:
            logger.error(f"Failed to save Scam Shield config: {e}")

    def get_stats(self) -> Dict[str, Any]:
        return {
            "messages_scanned": self.stats["messages_scanned"],
            "images_scanned": self.stats["images_scanned"],
            "scams_found": self.stats["scams_found"],
            "users_flagged": len(self.stats["users_flagged"])
        }

    def log_detection(self, user_id: int, username: str, channel_id: int, message_id: int, score: int, reasons: List[str], text: str, action: str, image_url: Optional[str] = None):
        self.stats["scams_found"] += 1
        self.stats["users_flagged"].add(user_id)
        
        event = {
            "timestamp": discord.utils.utcnow().isoformat(),
            "user_id": user_id,
            "username": username,
            "channel_id": channel_id,
            "message_id": message_id,
            "score": score,
            "reasons": reasons,
            "text": text[:200] + ("..." if len(text) > 200 else ""),
            "action": action,
            "image_url": image_url
        }
        self.history.append(event)
        # Cap history at 100 entries
        if len(self.history) > 100:
            self.history.pop(0)

    async def scan_url(self, text: str) -> Tuple[int, List[str]]:
        """Scans URL links inside text for shorteners or suspicious keywords."""
        score = 0
        reasons = []
        
        # Regex to find urls
        url_pattern = re.compile(r'https?://[^\s]+')
        urls = url_pattern.findall(text.lower())
        
        if not urls:
            return score, reasons

        shorteners = ["bit.ly", "tinyurl.com", "t.co", "is.gd", "buff.ly", "adf.ly", "tiny.cc", "qr.ae", "linktr.ee"]
        suspicious_keywords = ["nitro", "free", "gift", "giveaway", "steam", "claim", "drop", "airdrop", "bonus", "mrbeast", "usdt"]
        suspicious_tlds = [".xyz", ".club", ".ru", ".gift", ".free", ".top", ".info", ".biz", ".click", ".win"]

        for url in urls:
            # Check shorteners
            if any(sh in url for sh in shorteners):
                score += 25
                reasons.append(f"🔗 URL Shortener detected in link: `{url}`")
            
            # Extract domain
            domain_match = re.search(r'https?://([^/]+)', url)
            if domain_match:
                domain = domain_match.group(1)
                # Check suspicious keywords in domain
                matched_keywords = [kw for kw in suspicious_keywords if kw in domain]
                if matched_keywords:
                    score += 20
                    reasons.append(f"⚠️ Suspicious domain keyword(s) {matched_keywords} in: `{domain}`")
                
                # Check suspicious TLDs
                if any(domain.endswith(tld) for tld in suspicious_tlds):
                    score += 15
                    reasons.append(f"🌐 Suspicious top-level domain (TLD) in: `{domain}`")
                    
        return score, reasons

    async def scan_text_keywords(self, text: str) -> Tuple[int, List[str]]:
        """Calculate weighted keyword score for raw text content."""
        score = 0
        reasons = []
        text_lower = text.lower()

        keywords = {
            "mrbeast": 20,
            "bonus code": 20,
            "activate code": 20,
            "reward received": 25,
            "withdrawal successful": 25,
            "receive usdt": 15,
            "usdt": 15,
            "crypto reward": 20,
            "giveaway": 15,
            "free money": 20,
            "airdrop": 15,
            "investment return": 20,
            "profit guaranteed": 20,
            "instant withdrawal": 20
        }

        for kw, weight in keywords.items():
            # Match keywords, respecting boundary checks where necessary
            if kw in text_lower:
                score += weight
                reasons.append(f"🔑 Keyword Match: '{kw.upper()}' (+{weight})")

        return score, reasons

    async def extract_image_text_ocr(self, attachment: discord.Attachment) -> Tuple[str, Dict[str, Any]]:
        """Sends the image attachment to the BluesMinds Vision API (GPT-4o) for layout analysis and text extraction."""
        api_key = os.getenv("BLUESMINDS_API_KEY")
        base_url = os.getenv("BLUESMINDS_BASE", "https://api.bluesminds.com/v1")
        
        if not api_key:
            logger.error("BLUESMINDS_API_KEY not found. Skipping OCR.")
            return "", {"layout_score": 0, "layout_reasons": []}

        try:
            # Download file into bytes
            image_bytes = await attachment.read()
            
            # Compute file hash
            file_hash = hashlib.sha256(image_bytes).hexdigest()
            if file_hash in self.image_cache:
                cached = self.image_cache[file_hash]
                logger.info("Image OCR retrieved from cache.")
                return cached["text"], cached["layout_analysis"]

            self.stats["images_scanned"] += 1
            
            # Base64 encode
            base64_image = base64.b64encode(image_bytes).decode("utf-8")
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }
            
            # Prepare payload asking for both OCR text extraction and UI layout pattern checks
            payload = {
                "model": "gpt-4o",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "Analyze this image. First, transcribe all readable text precisely. "
                                    "Second, evaluate if this is a screenshot of a scam (e.g. fake crypto dashboard, fake withdrawal confirmation, fake bonus activation page, fake giveaway/airdrop banner, fake earning proofs). "
                                    "Identify indicators present: green profit panels, large payouts, celebrity/MrBeast branding, promo codes, transaction confirmations. "
                                    "Return the analysis STRICTLY in JSON format: "
                                    "{\n"
                                    "  \"extracted_text\": \"all text here\",\n"
                                    "  \"is_scam_layout\": true/false,\n"
                                    "  \"indicators\": [\"list of indicators found\"],\n"
                                    "  \"detected_layout_type\": \"type of dashboard or confirmation page\"\n"
                                    "}"
                                )
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                "max_tokens": 600,
                "response_format": {"type": "json_object"}
            }

            async with httpx.AsyncClient(timeout=45.0) as client:
                response = await client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
                
            if response.status_code == 200:
                res_data = response.json()
                content_text = res_data["choices"][0]["message"]["content"]
                parsed = json.loads(content_text)
                
                extracted_text = parsed.get("extracted_text", "")
                
                # Calculate layout risk score
                layout_score = 0
                layout_reasons = []
                
                if parsed.get("is_scam_layout", False):
                    layout_score += 25
                    layout_reasons.append(f"🖼️ Layout Pattern: Fake Dashboard/Confirmation layout ({parsed.get('detected_layout_type', 'scam screenshot')})")
                    
                indicators = parsed.get("indicators", [])
                for indicator in indicators:
                    layout_score += 15
                    layout_reasons.append(f"🎨 Layout Indicator: Found '{indicator}'")
                
                layout_analysis = {
                    "layout_score": layout_score,
                    "layout_reasons": layout_reasons
                }
                
                # Cache results
                self.image_cache[file_hash] = {
                    "text": extracted_text,
                    "layout_analysis": layout_analysis
                }
                
                return extracted_text, layout_analysis
            else:
                logger.error(f"Vision API returned status {response.status_code}: {response.text}")
                return "", {"layout_score": 0, "layout_reasons": []}
                
        except Exception as e:
            logger.error(f"Error executing OCR Vision extraction: {e}")
            return "", {"layout_score": 0, "layout_reasons": []}

    async def scan_message_scams(self, message: discord.Message) -> Tuple[int, List[str], str]:
        """Runs the multi-layered scan on a message. Returns total score, reasons, and raw text scanned."""
        self.stats["messages_scanned"] += 1
        
        total_score = 0
        all_reasons = []
        raw_text = message.content or ""
        
        # 1. Text keyword weights scan
        kw_score, kw_reasons = await self.scan_text_keywords(raw_text)
        total_score += kw_score
        all_reasons.extend(kw_reasons)
        
        # 2. URL link scanning
        link_score, link_reasons = await self.scan_url(raw_text)
        total_score += link_score
        all_reasons.extend(link_reasons)
        
        # 3. Image attachments OCR scan
        if message.attachments:
            for attachment in message.attachments:
                # Limit size (5 MB = 5 * 1024 * 1024 bytes)
                if attachment.size > 5 * 1024 * 1024:
                    logger.info(f"Skipping attachment {attachment.filename} due to size limit (>5MB).")
                    continue
                    
                # Support common images only
                if any(attachment.filename.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".webp"]):
                    extracted_text, layout_analysis = await self.extract_image_text_ocr(attachment)
                    
                    if extracted_text:
                        raw_text += " [extracted OCR: " + extracted_text + "]"
                        # Re-scan keywords on the extracted image text
                        img_kw_score, img_kw_reasons = await self.scan_text_keywords(extracted_text)
                        total_score += img_kw_score
                        # Modify reason descriptions for clarification
                        all_reasons.extend([r.replace("🔑 Keyword Match:", "🖼️ OCR Keyword:") for r in img_kw_reasons])
                        
                    # Add layout analysis additions
                    total_score += layout_analysis.get("layout_score", 0)
                    all_reasons.extend(layout_analysis.get("layout_reasons", []))

        # Clamp total score at 100
        total_score = min(total_score, 100)
        return total_score, all_reasons, raw_text
