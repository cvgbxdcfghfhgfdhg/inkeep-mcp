import re
import requests
from urllib.parse import urljoin, urlparse

class ConfigExtractor:
    def __init__(self, session=None):
        self.session = session or requests.Session()

    def scan(self, target_url):
        """
        Scans the target URL for Inkeep configuration (API Key, etc.)
        """
        try:
            res = self.session.get(target_url, timeout=15)
            if res.status_code != 200:
                return None
            
            # 1. Identify Script Candidates
            # Matches src="/path/to/script.js" or src='...'
            # Use triple quotes to avoid escaping issues
            script_pattern = r'src=["\']([^"\']+\.js[^"\']*)["\']'
            scripts = re.findall(script_pattern, res.text)
            
            base_url = f"{urlparse(target_url).scheme}://{urlparse(target_url).netloc}"
            
            candidates = []
            others = []
            
            # Prioritize likely candidates
            for s in scripts:
                full_s = urljoin(base_url, s)
                s_lower = s.lower()
                if 'inkeep' in s_lower:
                    candidates.insert(0, full_s)
                elif any(x in s_lower for x in ['layout', 'app', '_app', 'page', 'main']):
                    candidates.append(full_s)
                else:
                    others.append(full_s)
            
            final_list = list(dict.fromkeys(candidates + others))
            
            # 2. Scan Scripts
            patterns = [
                (r'apiKey\s*:\s*["\']([a-f0-9]{32,})["\']', "apiKey"),
                (r'integrationId\s*:\s*["\']([a-zA-Z0-9_-]{20,})["\']', "integrationId"),
                (r'organizationId\s*:\s*["\']([a-zA-Z0-9_-]{20,})["\']', "organizationId")
            ]
            
            # Limit to first 50 scripts to avoid taking too long
            for js_url in final_list[:50]:
                try:
                    js_res = self.session.get(js_url, timeout=5)
                    if js_res.status_code == 200:
                        for p, key_name in patterns:
                            match = re.search(p, js_res.text)
                            if match:
                                val = match.group(1)
                                if key_name == 'apiKey': # Primary target
                                    return {"apiKey": val}
                except Exception:
                    continue
            
            return None

        except Exception as e:
            return None