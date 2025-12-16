# services/audio_service.py
"""
Service for generating audio from lecture content using ElevenLabs TTS.
"""

import re
import httpx
from datetime import datetime

from logger import logger
from settings import settings
from supabase_config import BUCKETS, supabase


class AudioService:
    """Service for generating audio narration from lecture content using ElevenLabs."""

    # ElevenLabs API endpoint
    API_BASE_URL = "https://api.elevenlabs.io/v1"
    
    # ElevenLabs model options
    MODELS = {
        "eleven_multilingual_v2": {
            "name": "Multilingual v2",
            "description": "Lifelike, consistent quality. Best for long-form. 29 languages.",
            "max_chars": 10000,
        },
        "eleven_flash_v2_5": {
            "name": "Flash v2.5",
            "description": "Ultra-fast (~75ms latency). 32 languages. 50% lower cost.",
            "max_chars": 40000,
        },
        "eleven_turbo_v2_5": {
            "name": "Turbo v2.5",
            "description": "High quality, low latency (~250ms). Good balance.",
            "max_chars": 40000,
        },
    }
    DEFAULT_MODEL = "eleven_multilingual_v2"
    
    # Popular ElevenLabs voices (pre-made voices available to all users)
    # These are default voices available in ElevenLabs
    VOICES = {
        "rachel": {
            "id": "21m00Tcm4TlvDq8ikWAM",
            "name": "Rachel",
            "description": "Calm and professional American female voice",
        },
        "drew": {
            "id": "29vD33N1CtxCmqQRPOHJ",
            "name": "Drew",
            "description": "Well-rounded American male voice",
        },
        "clyde": {
            "id": "2EiwWnXFnvU5JabPnv8n",
            "name": "Clyde",
            "description": "War veteran character voice",
        },
        "paul": {
            "id": "5Q0t7uMcjvnagumLfvZi",
            "name": "Paul",
            "description": "Ground reporter style male voice",
        },
        "domi": {
            "id": "AZnzlk1XvdvUeBnXmlld",
            "name": "Domi",
            "description": "Strong and confident female voice",
        },
        "dave": {
            "id": "CYw3kZ02Hs0563khs1Fj",
            "name": "Dave",
            "description": "British conversational male voice",
        },
        "fin": {
            "id": "D38z5RcWu1voky8WS1ja",
            "name": "Fin",
            "description": "Sailor character Irish male voice",
        },
        "sarah": {
            "id": "EXAVITQu4vr4xnSDxMaL",
            "name": "Sarah",
            "description": "Soft and friendly American female voice",
        },
        "antoni": {
            "id": "ErXwobaYiN019PkySvjV",
            "name": "Antoni",
            "description": "Well-rounded American male voice",
        },
        "thomas": {
            "id": "GBv7mTt0atIp3Br8iCZE",
            "name": "Thomas",
            "description": "Calm American male voice",
        },
        "charlie": {
            "id": "IKne3meq5aSn9XLyUdCD",
            "name": "Charlie",
            "description": "Natural Australian male voice",
        },
        "george": {
            "id": "JBFqnCBsd6RMkjVDRZzb",
            "name": "George",
            "description": "Warm British narrator voice",
        },
        "emily": {
            "id": "LcfcDJNUP1GQjkzn1xUU",
            "name": "Emily",
            "description": "Calm and gentle American female voice",
        },
        "elli": {
            "id": "MF3mGyEYCl7XYWbV9V6O",
            "name": "Elli",
            "description": "Emotional American female voice",
        },
        "callum": {
            "id": "N2lVS1w4EtoT3dr4eOWO",
            "name": "Callum",
            "description": "Intense transatlantic male voice",
        },
        "patrick": {
            "id": "ODq5zmih8GrVes37Dizd",
            "name": "Patrick",
            "description": "Shouty male voice with character",
        },
        "harry": {
            "id": "SOYHLrjzK2X1ezoPC6cr",
            "name": "Harry",
            "description": "Anxious British male voice",
        },
        "liam": {
            "id": "TX3LPaxmHKxFdv7VOQHJ",
            "name": "Liam",
            "description": "Articulate American male voice",
        },
        "dorothy": {
            "id": "ThT5KcBeYPX3keUQqHPh",
            "name": "Dorothy",
            "description": "Pleasant British female voice",
        },
        "josh": {
            "id": "TxGEqnHWrfWFTfGW9XjX",
            "name": "Josh",
            "description": "Deep American male voice",
        },
        "arnold": {
            "id": "VR6AewLTigWG4xSOukaG",
            "name": "Arnold",
            "description": "Crisp American male voice",
        },
        "charlotte": {
            "id": "XB0fDUnXU5powFXDhCwa",
            "name": "Charlotte",
            "description": "Seductive Swedish female voice",
        },
        "alice": {
            "id": "Xb7hH8MSUJpSbSDYk0k2",
            "name": "Alice",
            "description": "Confident British female voice",
        },
        "matilda": {
            "id": "XrExE9yKIg1WjnnlVkGX",
            "name": "Matilda",
            "description": "Warm American female voice",
        },
        "james": {
            "id": "ZQe5CZNOzWyzPSCn5a3c",
            "name": "James",
            "description": "Deep Australian male voice",
        },
        "joseph": {
            "id": "Zlb1dXrM653N07WRdFW3",
            "name": "Joseph",
            "description": "British male voice",
        },
        "michael": {
            "id": "flq6f7yk4E4fJM5XTYuZ",
            "name": "Michael",
            "description": "Older American male voice",
        },
        "ethan": {
            "id": "g5CIjZEefAph4nQFvHAz",
            "name": "Ethan",
            "description": "Young American male voice",
        },
        "chris": {
            "id": "iP95p4xoKVk53GoZ742B",
            "name": "Chris",
            "description": "Casual American male voice",
        },
        "gigi": {
            "id": "jBpfuIE2acCO8z3wKNLl",
            "name": "Gigi",
            "description": "Childlike American female voice",
        },
        "freya": {
            "id": "jsCqWAovK2LkecY7zXl4",
            "name": "Freya",
            "description": "Expressive American female voice",
        },
        "brian": {
            "id": "nPczCjzI2devNBz1zQrb",
            "name": "Brian",
            "description": "Deep American narrator voice",
        },
        "grace": {
            "id": "oWAxZDx7w5VEj9dCyTzz",
            "name": "Grace",
            "description": "Southern American female voice",
        },
        "daniel": {
            "id": "onwK4e9ZLuTAKqWW03F9",
            "name": "Daniel",
            "description": "Deep British male voice",
        },
        "lily": {
            "id": "pFZP5JQG7iQjIQuC4Bku",
            "name": "Lily",
            "description": "Warm British female voice",
        },
        "serena": {
            "id": "pMsXgVXv3BLzUgSXRplE",
            "name": "Serena",
            "description": "Pleasant American female voice",
        },
        "adam": {
            "id": "pNInz6obpgDQGcFmaJgB",
            "name": "Adam",
            "description": "Deep American male voice",
        },
        "nicole": {
            "id": "piTKgcLEGmPE4e6mEKli",
            "name": "Nicole",
            "description": "Soft female whisper voice",
        },
        "bill": {
            "id": "pqHfZKP75CvOlQylNhV4",
            "name": "Bill",
            "description": "Trustworthy American male voice",
        },
        "jessie": {
            "id": "t0jbNlBVZ17f02VDIeMI",
            "name": "Jessie",
            "description": "Raspy American male voice",
        },
        "sam": {
            "id": "yoZ06aMxZJJ28mfd3POQ",
            "name": "Sam",
            "description": "Raspy American male voice",
        },
        "glinda": {
            "id": "z9fAnlkpzviPz146aGWa",
            "name": "Glinda",
            "description": "Witch character female voice",
        },
        "giovanni": {
            "id": "zcAOhNBS3c14rBihAFp1",
            "name": "Giovanni",
            "description": "Italian accented male voice",
        },
        "mimi": {
            "id": "zrHiDhphv9ZnVXBqCLjz",
            "name": "Mimi",
            "description": "Childish Swedish female voice",
        },
    }
    DEFAULT_VOICE = "george"  # Great for narration - warm British narrator
    
    def __init__(self, db=None):
        """Initialize the audio service."""
        self.db = db
        self.api_key = settings.ELEVENLABS_API_KEY
        
        if not self.api_key:
            logger.warning("ELEVENLABS_API_KEY not set. Audio generation will fail.")

    async def generate_audio_for_lecture(
        self,
        lecture_id: str,
        lecture_content: str,
        lecture_title: str,
        voice: str | None = None,
        model: str | None = None,
    ) -> dict:
        """
        Generate audio narration for a lecture using ElevenLabs TTS.
        
        Args:
            lecture_id: UUID of the lecture
            lecture_content: Full text content of the lecture
            lecture_title: Title of the lecture (for file naming)
            voice: Voice key (e.g., 'george', 'rachel') or voice_id
            model: Model ID (eleven_multilingual_v2, eleven_flash_v2_5, eleven_turbo_v2_5)
            
        Returns:
            Dictionary with audio file information
        """
        try:
            if not self.api_key:
                raise ValueError("ELEVENLABS_API_KEY is not configured")
            
            # Resolve voice
            voice_key = voice or self.DEFAULT_VOICE
            voice_info = self.VOICES.get(voice_key.lower())
            
            if voice_info:
                voice_id = voice_info["id"]
                voice_name = voice_info["name"]
            else:
                # Assume it's a direct voice_id
                voice_id = voice_key
                voice_name = voice_key
            
            # Resolve model
            model_id = model or self.DEFAULT_MODEL
            if model_id not in self.MODELS:
                model_id = self.DEFAULT_MODEL
                logger.warning(f"Invalid model specified, using default: {model_id}")
            
            model_info = self.MODELS[model_id]
            max_chars = model_info["max_chars"]
            
            logger.info(
                f"Generating audio for lecture {lecture_id} "
                f"using voice '{voice_name}' ({voice_id}) and model '{model_id}'"
            )
            
            # Prepare content for TTS (clean up markdown, etc.)
            clean_content = self._prepare_content_for_speech(lecture_content)
            
            # Split content into chunks if too long
            chunks = self._split_content(clean_content, max_chars)
            logger.info(f"Split content into {len(chunks)} chunks for TTS")
            
            # Generate audio for each chunk
            audio_segments = []
            async with httpx.AsyncClient(timeout=120.0) as client:
                for idx, chunk in enumerate(chunks):
                    logger.info(f"Generating audio chunk {idx + 1}/{len(chunks)}")
                    
                    response = await client.post(
                        f"{self.API_BASE_URL}/text-to-speech/{voice_id}",
                        headers={
                            "xi-api-key": self.api_key,
                            "Content-Type": "application/json",
                            "Accept": "audio/mpeg",
                        },
                        json={
                            "text": chunk,
                            "model_id": model_id,
                            "voice_settings": {
                                "stability": 0.5,
                                "similarity_boost": 0.75,
                                "style": 0.0,
                                "use_speaker_boost": True,
                            },
                        },
                    )
                    
                    if response.status_code != 200:
                        error_detail = response.text
                        logger.error(f"ElevenLabs API error: {response.status_code} - {error_detail}")
                        raise Exception(f"ElevenLabs API error: {response.status_code}")
                    
                    audio_segments.append(response.content)
            
            # Combine audio segments
            combined_audio = b"".join(audio_segments)
            
            # Generate file name
            safe_title = self._sanitize_filename(lecture_title)
            audio_filename = f"{safe_title}_audio.mp3"
            storage_path = f"lectures/{lecture_id}/audio/{audio_filename}"
            
            # Upload to Supabase storage
            bucket_name = BUCKETS["GENERATED_CONTENT"]
            
            try:
                supabase.upload_file(
                    bucket_name=bucket_name,
                    file_path=storage_path,
                    file_data=combined_audio,
                    file_options={"content-type": "audio/mpeg"},
                )
                logger.info(f"Audio uploaded to {bucket_name}/{storage_path}")
            except Exception as upload_error:
                # If file exists, try to remove and re-upload
                error_str = str(upload_error).lower()
                if "already exists" in error_str or "duplicate" in error_str:
                    logger.info("Audio file exists, replacing...")
                    supabase.delete_file(bucket_name, storage_path)
                    supabase.upload_file(
                        bucket_name=bucket_name,
                        file_path=storage_path,
                        file_data=combined_audio,
                        file_options={"content-type": "audio/mpeg"},
                    )
                else:
                    raise upload_error
            
            # Get download URL
            bucket = supabase.get_storage_bucket(bucket_name)
            download_url = bucket.get_public_url(storage_path)
            
            # Calculate duration estimate (rough: ~150 words per minute)
            word_count = len(clean_content.split())
            duration_minutes = word_count / 150
            duration_seconds = int(duration_minutes * 60)
            
            result = {
                "lecture_id": lecture_id,
                "audio_filename": audio_filename,
                "storage_path": storage_path,
                "storage_bucket": bucket_name,
                "file_size": len(combined_audio),
                "mime_type": "audio/mpeg",
                "download_url": download_url,
                "voice": voice_name,
                "voice_id": voice_id,
                "model": model_id,
                "model_name": model_info["name"],
                "chunks_processed": len(chunks),
                "estimated_duration_seconds": duration_seconds,
                "created_at": datetime.utcnow().isoformat(),
            }
            
            logger.info(
                f"Audio generated successfully for lecture {lecture_id}: "
                f"{len(combined_audio)} bytes, ~{duration_seconds}s duration"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error generating audio for lecture {lecture_id}: {e!s}")
            raise

    def _prepare_content_for_speech(self, content: str) -> str:
        """
        Prepare lecture content for text-to-speech by cleaning up formatting.
        
        Removes markdown syntax, normalizes whitespace, and makes text
        more suitable for natural speech.
        """
        if not content:
            return ""
        
        text = content
        
        # Remove markdown headers (## Header -> Header)
        text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
        
        # Remove bold/italic markdown
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)  # **bold**
        text = re.sub(r"\*(.+?)\*", r"\1", text)  # *italic*
        text = re.sub(r"__(.+?)__", r"\1", text)  # __bold__
        text = re.sub(r"_(.+?)_", r"\1", text)  # _italic_
        
        # Remove code blocks
        text = re.sub(r"```[\s\S]*?```", " [code example omitted] ", text)
        text = re.sub(r"`([^`]+)`", r"\1", text)  # inline code
        
        # Remove links but keep text
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        
        # Remove bullet points and numbered lists formatting
        text = re.sub(r"^[\s]*[-*+]\s+", "", text, flags=re.MULTILINE)
        text = re.sub(r"^[\s]*\d+\.\s+", "", text, flags=re.MULTILINE)
        
        # Remove horizontal rules
        text = re.sub(r"^[-*_]{3,}$", "", text, flags=re.MULTILINE)
        
        # Normalize whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)  # Max 2 newlines
        text = re.sub(r"[ \t]+", " ", text)  # Single spaces
        
        # Clean up any remaining special characters that might cause issues
        text = text.replace("&nbsp;", " ")
        text = text.replace("&amp;", "and")
        text = text.replace("&lt;", "less than")
        text = text.replace("&gt;", "greater than")
        
        return text.strip()

    def _split_content(self, content: str, max_chars: int = 5000) -> list[str]:
        """
        Split content into chunks suitable for TTS API.
        
        Tries to split at sentence boundaries to maintain natural speech flow.
        ElevenLabs recommends keeping chunks reasonable for best quality.
        """
        # Use a conservative limit below the max to ensure quality
        effective_max = min(max_chars, 5000)
        
        if len(content) <= effective_max:
            return [content]
        
        chunks = []
        current_chunk = ""
        
        # Split by sentences (roughly)
        sentences = content.replace("\n", " ").split(". ")
        
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            
            # Add period back if it was removed
            if not sentence.endswith((".", "!", "?", ":")):
                sentence = sentence + "."
            
            # Check if adding this sentence would exceed limit
            if len(current_chunk) + len(sentence) + 1 > effective_max:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence
            else:
                current_chunk += " " + sentence if current_chunk else sentence
        
        # Add remaining content
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for safe storage."""
        # Remove or replace invalid characters
        safe = re.sub(r'[<>:"/\\|?*]', "", filename)
        safe = re.sub(r"\s+", "_", safe)
        safe = safe[:100]  # Limit length
        return safe or "lecture"

    async def delete_lecture_audio(self, lecture_id: str) -> bool:
        """
        Delete audio file for a lecture.
        
        Args:
            lecture_id: UUID of the lecture
            
        Returns:
            True if deleted successfully
        """
        try:
            # Get audio content record
            if self.db:
                audio_records = self.db.get_records(
                    "lecture_content",
                    {"lecture_id": lecture_id, "file_type": "mp3"}
                )
                
                for record in audio_records:
                    storage_path = record.get("storage_path")
                    bucket_name = record.get("storage_bucket")
                    
                    if storage_path and bucket_name:
                        try:
                            supabase.delete_file(bucket_name, storage_path)
                            logger.info(f"Deleted audio file: {storage_path}")
                        except Exception as e:
                            logger.warning(f"Could not delete audio file {storage_path}: {e}")
                    
                    # Delete the record
                    self.db.delete_record("lecture_content", record["id"])
                
                return True
            return False
            
        except Exception as e:
            logger.error(f"Error deleting audio for lecture {lecture_id}: {e!s}")
            return False

    @staticmethod
    def get_available_voices() -> list[dict]:
        """Get list of available TTS voices with descriptions."""
        voices = []
        for key, info in AudioService.VOICES.items():
            voices.append({
                "id": key,
                "voice_id": info["id"],
                "name": info["name"],
                "description": info["description"],
            })
        return sorted(voices, key=lambda x: x["name"])

    @staticmethod
    def get_available_models() -> list[dict]:
        """Get list of available TTS models with descriptions."""
        models = []
        for model_id, info in AudioService.MODELS.items():
            models.append({
                "id": model_id,
                "name": info["name"],
                "description": info["description"],
                "max_chars": info["max_chars"],
            })
        return models
