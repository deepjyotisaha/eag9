import os
import re
import json
import yaml
import validators
from pathlib import Path
from typing import Tuple, Dict, List, Optional, Any
import hashlib
from urllib.parse import urlparse
import mimetypes
import logging
import httpx
import asyncio

logger = logging.getLogger(__name__)

class BaseValidator:
    def __init__(self):
        self.config = self._load_config()
    
    def _load_config(self) -> Dict:
        config_path = Path("config/profiles.yaml")
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            return config.get('validation', {})
        except Exception as e:
            logger.error(f"Error loading config: {str(e)}")
            return {}

class InputValidator:
    def __init__(self):
        self.config = self._load_config()
        self.sensitive_patterns = self._load_sensitive_patterns()
        self.blocked_words = self._load_blocked_words()
        self.supported_languages = self.config.get('supported_languages', ['python', 'sql', 'javascript'])
        
    def _load_config(self) -> Dict:
        """Load configuration from profiles.yaml"""
        config_path = Path("config/profiles.yaml")
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        return config.get('validation', {
            'max_file_size_mb': 5,
            'max_query_length': 1000,
            'supported_languages': ['python', 'sql', 'javascript']
        })

    def _load_sensitive_patterns(self) -> List[str]:
        """Load patterns for sensitive information detection"""
        patterns_path = Path("config/sensitive_patterns.txt")
        if patterns_path.exists():
            with open(patterns_path, 'r') as f:
                return [line.strip() for line in f if line.strip()]
        return [
            r'password\s*=\s*["\']\w+["\']',
            r'api[_-]?key\s*=\s*["\']\w+["\']',
            r'secret\s*=\s*["\']\w+["\']',
            r'aws[_-]?key\s*=\s*["\']\w+["\']',
            r'private[_-]?key\s*=\s*["\']\w+["\']'
        ]

    def _load_blocked_words(self) -> List[str]:
        """Load blocked words for content filtering"""
        blocked_path = Path("config/blocked_words.txt")
        if blocked_path.exists():
            with open(blocked_path, 'r') as f:
                return [line.strip() for line in f if line.strip()]
        return []  # Default empty list, should be populated with actual blocked words

    def check_file_size(self, file_path: str) -> Tuple[str, Optional[str]]:
        """Check if file exists and is within size limit"""
        try:
            # Normalize and validate file path
            file_path = os.path.normpath(file_path)
            if '..' in file_path or file_path.startswith('/'):
                return "dont_process", "Invalid file path"
            
            if not os.path.exists(file_path):
                return "dont_process", "File not found"
            
            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
            max_size = self.config.get('max_file_size_mb', 5)
            
            if file_size_mb > max_size:
                return "dont_process", f"File size exceeds maximum limit of {max_size}MB"
            return "process", None
        except Exception as e:
            return "dont_process", f"Error checking file size: {str(e)}"

    async def check_url_reachability(self, url: str) -> Tuple[str, Optional[str]]:
        """Check if URL is reachable"""
        try:
            # Add scheme if missing
            if not urlparse(url).scheme:
                url = 'https://' + url

            async with httpx.AsyncClient(timeout=5.0) as client:
                try:
                    response = await client.head(url, follow_redirects=True)
                    if response.status_code >= 400:
                        return "dont_process", f"URL returned error status code: {response.status_code}"
                    return "process", None
                except httpx.RequestError as e:
                    return "dont_process", f"URL is not reachable: {str(e)}"
        except Exception as e:
            logger.error(f"URL reachability check error: {str(e)}")
            return "dont_process", f"URL validation error: {str(e)}"

    def check_url(self, url: str) -> Tuple[str, Optional[str]]:
        """Validate URL format and accessibility"""
        try:
            # Add scheme if missing
            if not urlparse(url).scheme:
                url = 'https://' + url

            # Basic URL format validation
            if not validators.url(url):
                return "dont_process", "Invalid URL format"

            # Check URL length
            if len(url) > 2048:  # Standard URL length limit
                return "dont_process", "URL exceeds maximum length"

            # Check for valid domain
            domain = urlparse(url).netloc
            if not domain or '.' not in domain:
                return "dont_process", "Invalid domain name"

            # Check for common TLDs
            valid_tlds = ['.com', '.org', '.net', '.edu', '.gov', '.io', '.co', '.info']
            if not any(domain.endswith(tld) for tld in valid_tlds):
                return "dont_process", "Invalid top-level domain"

            # Check for valid characters in domain
            if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9-]{0,61}[a-zA-Z0-9](?:\.[a-zA-Z]{2,})+$', domain):
                return "dont_process", "Invalid domain name format"

            # Check URL reachability
            loop = asyncio.get_event_loop()
            status, message = loop.run_until_complete(self.check_url_reachability(url))
            if status == "dont_process":
                return status, message

            return "process", None
        except Exception as e:
            logger.error(f"URL validation error: {str(e)}")
            return "dont_process", f"URL validation error: {str(e)}"

    def check_query_length(self, query: str) -> Tuple[str, Optional[str]]:
        """Check if query length is within limits"""
        max_length = self.config.get('max_query_length', 1000)
        if len(query) > max_length:
            return "dont_process", f"Query length exceeds maximum limit of {max_length} characters"
        return "process", None

    def check_code_injection(self, query: str) -> Tuple[str, Optional[str]]:
        """Check for potential code injection"""
        # First, check if the query is a simple URL or file request
        if re.match(r'^(?:get|fetch|download|read|summarize|extract).*(?:from|at|in|on).*(?:http|www|\.com|\.org|\.net|\.io)', query, re.IGNORECASE):
            return "process", None

        for lang in self.supported_languages:
            patterns = {
                'python': r'(?i)(?:^|\s)(?:import\s+\w+|def\s+\w+|class\s+\w+|from\s+\w+\s+import|as\s+\w+|try|except|finally|with|async|await|eval|exec|__import__)(?:\s|$)',
                'sql': r'(?i)(?:^|\s)(?:SELECT\s+\w+|INSERT\s+INTO|UPDATE\s+\w+|DELETE\s+FROM|DROP\s+TABLE|ALTER\s+TABLE|CREATE\s+TABLE|TRUNCATE\s+TABLE|UNION\s+ALL|JOIN\s+\w+|WHERE\s+\w+)(?:\s|$)',
                'javascript': r'(?i)(?:^|\s)(?:function\s+\w+|var\s+\w+|let\s+\w+|const\s+\w+|=>|async\s+function|await\s+\w+|eval\s*\(|setTimeout\s*\(|setInterval\s*\()(?:\s|$)',
                'shell': r'(?i)(?:^|\s)(?:rm\s+-|del\s+/|mkdir\s+-|rmdir\s+/|chmod\s+\d+|chown\s+\w+|sudo\s+\w+|su\s+\w+|bash\s+-|sh\s+-)(?:\s|$)'
            }
            if re.search(patterns.get(lang, ''), query):
                logger.debug(f"Code injection check failed for language {lang} with pattern: {patterns.get(lang, '')}")
                return "dont_process", f"Potential {lang} code injection detected"
        return "process", None

    def check_blocked_content(self, text: str) -> Tuple[str, Optional[str]]:
        """Check for blocked words and content"""
        text_lower = text.lower()
        for word in self.blocked_words:
            if word.lower() in text_lower:
                return "dont_process", "Content contains blocked words"
        return "process", None

    def check_file_corruption(self, file_path: str) -> Tuple[str, Optional[str]]:
        """Check if file is corrupted"""
        try:
            with open(file_path, 'rb') as f:
                # Read first few bytes to check if file is readable
                f.read(1024)
            return "process", None
        except Exception as e:
            return "dont_process", f"File appears to be corrupted: {str(e)}"

    def check_sensitive_info(self, text: str) -> Tuple[str, Optional[str]]:
        """Check for sensitive information"""
        for pattern in self.sensitive_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return "dont_process", "Sensitive information detected"
        return "process", None

    async def validate_input(self, query: str) -> Tuple[str, Optional[str]]:
        """Main validation function that runs all checks"""
        try:
            # 1. Check query length
            max_length = self.config.get('max_query_length', 1000)
            if len(query) > max_length:
                return "dont_process", f"Query length exceeds maximum limit of {max_length} characters"

            # 2. Check for blocked content
            text_lower = query.lower()
            for word in self.blocked_words:
                if word.lower() in text_lower:
                    return "dont_process", "Content contains blocked words"

            # 3. Check for code injection
            status, message = self.check_code_injection(query)
            if status == "dont_process":
                return status, message

            # 4. Check for sensitive information
            status, message = self.check_sensitive_info(query)
            if status == "dont_process":
                return status, message

            # 5. Check for file paths
            file_paths = re.findall(r'[\w\-\.]+\.(?:pdf|txt|doc|docx|json|yaml|yml|py|sql|js)', query)
            for file_path in file_paths:
                # Check file size
                status, message = self.check_file_size(file_path)
                if status == "dont_process":
                    return status, message
                # Check file corruption
                status, message = self.check_file_corruption(file_path)
                if status == "dont_process":
                    return status, message

            # 6. Check for URLs
            urls = re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', query)
            # Also check for URLs without protocol
            urls.extend(re.findall(r'(?:^|\s)(?:www\.)?[a-zA-Z0-9][a-zA-Z0-9-]{0,61}[a-zA-Z0-9](?:\.[a-zA-Z]{2,})+', query))
            
            for url in urls:
                # First check URL format
                status, message = self.check_url(url)
                if status == "dont_process":
                    return status, message
                
                # Then check URL reachability
                status, message = await self.check_url_reachability(url)
                if status == "dont_process":
                    return status, message

            # 7. Check for empty or whitespace-only query
            if not query.strip():
                return "dont_process", "Empty query"

            # 8. Check for minimum query length
            min_length = self.config.get('min_query_length', 3)
            if len(query.strip()) < min_length:
                return "dont_process", f"Query too short (minimum {min_length} characters)"

            return "process", None
        except Exception as e:
            logger.error(f"Error in input validation: {str(e)}")
            return "dont_process", f"Validation error: {str(e)}"

def json_validator(response: str) -> bool:
    """Validate if response is valid JSON"""
    try:
        json.loads(response)
        return True
    except json.JSONDecodeError:
        return False

class OutputValidator:
    def __init__(self):
        self.blocked_words = self._load_blocked_words()
        self.config = self._load_config()

    def _load_blocked_words(self) -> List[str]:
        """Load blocked words for content filtering"""
        blocked_path = Path("config/blocked_words.txt")
        if blocked_path.exists():
            with open(blocked_path, 'r') as f:
                return [line.strip() for line in f if line.strip()]
        return []

    def _load_config(self) -> Dict:
        """Load configuration from profiles.yaml"""
        config_path = Path("config/profiles.yaml")
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        return config.get('validation', {
            'max_output_length': 10000
        })

    def validate_output(self, response: str) -> Tuple[bool, Optional[str]]:
        """Validate output for inappropriate content"""
        try:
            if not isinstance(response, str):
                return False, "Response must be a string"
                
            response_lower = response.lower()
            
            # Check for blocked words
            for word in self.blocked_words:
                if word.lower() in response_lower:
                    return False, f"Response contains blocked word: {word}"
                    
            # Check for excessive length
            max_length = self.config.get('max_output_length', 10000)
            if len(response) > max_length:
                return False, f"Response exceeds maximum length of {max_length} characters"
                
            return True, None
        except Exception as e:
            logger.error(f"Output validation error: {str(e)}")
            return False, f"Output validation error: {str(e)}"

class JsonValidator:
    def __init__(self):
        self.config = self._load_config()
        
    def _load_config(self) -> Dict:
        """Load configuration from profiles.yaml"""
        config_path = Path("config/profiles.yaml")
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        return config.get('validation', {
            'max_json_depth': 10,
            'max_json_size_kb': 1024,
            'allowed_json_types': ['str', 'int', 'float', 'bool', 'list', 'dict', 'null']
        })

    def validate_json_structure(self, json_str: str) -> Tuple[bool, Optional[str]]:
        """Validate JSON structure and format"""
        try:
            # Check if string is valid JSON
            json_obj = json.loads(json_str)
            
            # Check JSON size
            json_size_kb = len(json_str.encode('utf-8')) / 1024
            max_size = self.config.get('max_json_size_kb', 1024)
            if json_size_kb > max_size:
                return False, f"JSON size exceeds maximum limit of {max_size}KB"
            
            # Check JSON depth
            depth = self._get_json_depth(json_obj)
            max_depth = self.config.get('max_json_depth', 10)
            if depth > max_depth:
                return False, f"JSON depth exceeds maximum limit of {max_depth}"
            
            # Check for allowed types
            if not self._validate_json_types(json_obj):
                return False, "JSON contains unsupported data types"
            
            return True, None
        except json.JSONDecodeError as e:
            return False, f"Invalid JSON format: {str(e)}"
        except Exception as e:
            return False, f"JSON validation error: {str(e)}"

    def _get_json_depth(self, obj: Any, current_depth: int = 0) -> int:
        """Calculate the maximum depth of a JSON object"""
        if not isinstance(obj, (dict, list)):
            return current_depth
        
        max_depth = current_depth
        if isinstance(obj, dict):
            for value in obj.values():
                depth = self._get_json_depth(value, current_depth + 1)
                max_depth = max(max_depth, depth)
        elif isinstance(obj, list):
            for item in obj:
                depth = self._get_json_depth(item, current_depth + 1)
                max_depth = max(max_depth, depth)
        
        return max_depth

    def _validate_json_types(self, obj: Any) -> bool:
        """Validate that all values in JSON are of allowed types"""
        allowed_types = self.config.get('allowed_json_types', ['str', 'int', 'float', 'bool', 'list', 'dict', 'null'])
        
        if obj is None and 'null' in allowed_types:
            return True
        
        obj_type = type(obj).__name__
        if obj_type in allowed_types:
            if obj_type in ('list', 'dict'):
                if isinstance(obj, list):
                    return all(self._validate_json_types(item) for item in obj)
                else:  # dict
                    return all(self._validate_json_types(value) for value in obj.values())
            return True
        
        return False

    def validate(self, json_str: str) -> Tuple[bool, Optional[str]]:
        """Main validation method that runs all JSON checks"""
        try:
            # Add input validation
            if not isinstance(json_str, str):
                return False, "Input must be a string"
                
            if not json_str.strip():
                return False, "Empty JSON string"
                
            return self.validate_json_structure(json_str)
        except Exception as e:
            logger.error(f"JSON validation error: {str(e)}")
            return False, f"JSON validation error: {str(e)}"
