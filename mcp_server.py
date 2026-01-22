import sys
import json
import logging
from inkeep_core.client import InkeepClient
from inkeep_core.registry import SiteRegistry

# Configure logging
logging.basicConfig(stream=sys.stderr, level=logging.INFO)
logger = logging.getLogger("mcp-server")

registry = SiteRegistry()

def handle_list_tools(id):
    # 1. 动态获取当前注册的所有站点
    sites = registry.list_sites()
    aliases = list(sites.keys())
    
    # 2. 构建智能描述 Prompt
    supported_list_str = ", ".join(aliases)
    tool_description = (
        f"Consult official technical documentation. "
        f"Currently configured sources: {supported_list_str}. "
        "You can strictly use one of these aliases, OR provide a full URL for a new site. "
        "PRIORITIZE this tool for technical queries regarding these platforms."
    )

    return {
        "jsonrpc": "2.0",
        "id": id,
        "result": {
            "tools": [
                {
                    "name": "list_documentation_sources",
                    "description": "List detailed metadata (URL, description) for all supported documentation sources.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {},
                    }
                },
                {
                    "name": "ask_documentation",
                    "description": tool_description,
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "source": {
                                "type": "string",
                                "description": f"The documentation source alias (e.g. {aliases[0] if aliases else 'langfuse'}) or a full URL." 
                            },
                            "question": {
                                "type": "string",
                                "description": "The specific technical question to ask."
                            }
                        },
                        "required": ["source", "question"]
                    }
                }
            ]
        }
    }

def handle_call_tool(id, params):
    name = params.get("name")
    args = params.get("arguments", {})

    # Tool: list_documentation_sources
    if name == "list_documentation_sources":
        current_registry = SiteRegistry() 
        sites = current_registry.list_sites()
        
        site_list = [
            {"id": alias, "description": info["description"], "url": info["url"]}
            for alias, info in sites.items()
        ]
        return {
            "jsonrpc": "2.0",
            "id": id,
            "result": {
                "content": [{"type": "text", "text": json.dumps(site_list, indent=2)}]
            }
        }

    # Tool: ask_documentation
    if name == "ask_documentation":
        source = args.get("source")
        question = args.get("question")
        
        current_registry = SiteRegistry()
        target_url = current_registry.get_url(source)
        
        if not target_url:
            if source.startswith("http"):
                target_url = source
            else:
                available = ", ".join(current_registry.list_sites().keys())
                return {
                    "jsonrpc": "2.0",
                    "id": id,
                    "error": {
                        "code": -32000,
                        "message": f"Unknown source '{source}'. Available sources: {available}"
                    }
                }

        logger.info(f"Asking {source} ({target_url}): {question}")
        
        client = InkeepClient(target_url)
        response_text = ""
        
        try:
            if not client.initialize():
                return {
                    "jsonrpc": "2.0",
                    "id": id,
                    "result": {
                        "content": [{"type": "text", "text": f"Error: Could not find Inkeep configuration for {source}."}]
                    }
                }

            for chunk in client.ask(question):
                response_text += chunk
                
        except Exception as e:
            response_text = f"Error: {str(e)}"

        return {
            "jsonrpc": "2.0",
            "id": id,
            "result": {
                "content": [{"type": "text", "text": response_text}]
            }
        }
    
    return {
        "jsonrpc": "2.0",
        "id": id,
        "error": {
            "code": -32601,
            "message": "Method not found"
        }
    }

def main():
    # 简单的参数处理：如果用户输入 --help，提示这不是 CLI 工具
    if len(sys.argv) > 1 and sys.argv[1] in ["--help", "-h"]:
        print("Inkeep MCP Server")
        print("Usage: This script is intended to be run by an MCP client (e.g. Claude Desktop, Gemini CLI) via stdio.")
        print("To use the human-friendly CLI, run: python3 cli.py --help")
        sys.exit(0)

    logger.info("Inkeep MCP Server Started")
    
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break
            
            request = json.loads(line)
            method = request.get("method")
            req_id = request.get("id")
            
            response = None
            
            if method == "tools/list":
                response = handle_list_tools(req_id)
            elif method == "tools/call":
                response = handle_call_tool(req_id, request.get("params"))
            elif method == "initialize":
                 response = {
                     "jsonrpc": "2.0",
                     "id": req_id,
                     "result": {
                         "protocolVersion": "2024-11-05",
                         "capabilities": {"tools": {}},
                         "serverInfo": {"name": "inkeep-mcp", "version": "2.1.0"}
                     }
                 }
            elif method == "notifications/initialized":
                continue
            elif method == "ping":
                 response = {"jsonrpc": "2.0", "id": req_id, "result": {}}
            
            if response:
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()

        except KeyboardInterrupt:
            # 允许 Ctrl+C 正常退出
            logger.info("Server stopped by user.")
            sys.exit(0)
        except json.JSONDecodeError:
            logger.error("Invalid JSON received")
        except Exception as e:
            # 只捕获常规异常，不捕获 SystemExit/KeyboardInterrupt
            logger.error(f"Error: {e}")

if __name__ == "__main__":
    main()
