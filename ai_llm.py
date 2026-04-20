#!/usr/bin/env python3
"""
MyanOS — AI/LLM Integration Module
Uses Manus.im Forge API (Gemini 2.5 Flash) for AI capabilities

Ported from colab-mobile-ai/server/_core/llm.ts to Python
Features:
  - Chat completions
  - Tool/function calling
  - Response format (JSON, text)
  - Thinking budget support
"""

import json
import urllib.request
import urllib.error
import os

# ─── Config ────────────────────────────────────────────────────────────────────
# Manus.im Forge API — same as colab repos use
FORGE_API_URL = os.environ.get('FORGE_API_URL', 'https://forge.manus.im/v1/chat/completions')
FORGE_API_KEY = os.environ.get('FORGE_API_KEY', '')

# Default model (same as colab repos)
DEFAULT_MODEL = 'gemini-2.5-flash'
MAX_TOKENS = 32768
THINKING_BUDGET = 128


def invoke_llm(messages, tools=None, tool_choice=None, max_tokens=None,
               response_format=None, model=None, api_key=None):
    """
    Send a chat completion request to the LLM API.

    Args:
        messages: List of dicts with 'role' and 'content' keys
                  Roles: 'system', 'user', 'assistant', 'tool'
        tools: Optional list of tool definitions (function calling)
        tool_choice: Optional tool choice ('auto', 'none', 'required', or {'name': str})
        max_tokens: Max response tokens (default 32768)
        response_format: Optional response format ('json_object', 'text', or schema)
        model: Model name (default 'gemini-2.5-flash')
        api_key: API key (falls back to FORGE_API_KEY env var)

    Returns:
        dict: API response with 'choices', 'usage', etc.
    """
    key = api_key or FORGE_API_KEY
    if not key:
        raise ValueError("FORGE_API_KEY not configured. Set FORGE_API_KEY environment variable.")

    # Build payload
    payload = {
        'model': model or DEFAULT_MODEL,
        'messages': _normalize_messages(messages),
        'max_tokens': max_tokens or MAX_TOKENS,
        'thinking': {'budget_tokens': THINKING_BUDGET},
    }

    if tools:
        payload['tools'] = tools

    if tool_choice:
        payload['tool_choice'] = _normalize_tool_choice(tool_choice, tools)

    if response_format:
        payload['response_format'] = response_format

    # Make request
    req_data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        FORGE_API_URL,
        data=req_data,
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {key}',
        },
        method='POST',
    )

    try:
        resp = urllib.request.urlopen(req, timeout=120)
        body = resp.read().decode('utf-8')
        return json.loads(body)
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8', errors='replace')
        raise RuntimeError(f"LLM API error {e.code}: {error_body}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"LLM connection failed: {e.reason}")


def _normalize_messages(messages):
    """Normalize message format for API compatibility"""
    normalized = []
    for msg in messages:
        role = msg.get('role', 'user')
        content = msg.get('content', '')

        # Handle tool messages
        if role in ('tool', 'function'):
            if isinstance(content, list):
                content = '\n'.join(
                    item.get('text', json.dumps(item)) if isinstance(item, dict) else str(item)
                    for item in content
                )
            normalized.append({
                'role': role,
                'content': str(content),
                'tool_call_id': msg.get('tool_call_id', ''),
            })
        else:
            # Handle multimodal content
            if isinstance(content, list):
                parts = []
                for item in content:
                    if isinstance(item, str):
                        parts.append({'type': 'text', 'text': item})
                    elif isinstance(item, dict):
                        parts.append(item)
                normalized.append({'role': role, 'content': parts})
            else:
                normalized.append({'role': role, 'content': content})

    return normalized


def _normalize_tool_choice(choice, tools):
    """Normalize tool_choice parameter"""
    if choice in ('none', 'auto'):
        return choice
    if choice == 'required':
        if not tools or len(tools) > 1:
            raise ValueError("tool_choice 'required' needs exactly one tool")
        return {'type': 'function', 'function': {'name': tools[0]['function']['name']}}
    if isinstance(choice, dict) and 'name' in choice:
        return {'type': 'function', 'function': {'name': choice['name']}}
    return choice


# ─── Helper Functions ──────────────────────────────────────────────────────────

def chat_simple(system_prompt, user_message, api_key=None, model=None):
    """Simple chat without tool calling"""
    response = invoke_llm(
        messages=[
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_message},
        ],
        api_key=api_key,
        model=model,
    )
    content = response.get('choices', [{}])[0].get('message', {}).get('content', '')
    return content if isinstance(content, str) else json.dumps(content)


def chat_with_history(messages, api_key=None, model=None):
    """Chat with conversation history"""
    response = invoke_llm(messages=messages, api_key=api_key, model=model)
    content = response.get('choices', [{}])[0].get('message', {}).get('content', '')
    return content if isinstance(content, str) else json.dumps(content)


def chat_with_tools(system_prompt, user_message, tools, api_key=None):
    """Chat with function/tool calling"""
    messages = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': user_message},
    ]
    response = invoke_llm(
        messages=messages,
        tools=tools,
        tool_choice='auto',
        api_key=api_key,
    )
    return response


def extract_response_text(response):
    """Extract text content from LLM response"""
    choices = response.get('choices', [])
    if not choices:
        return ''
    message = choices[0].get('message', {})
    content = message.get('content', '')
    return content if isinstance(content, str) else json.dumps(content)


def extract_tool_calls(response):
    """Extract tool calls from LLM response"""
    choices = response.get('choices', [])
    if not choices:
        return []
    message = choices[0].get('message', {})
    return message.get('tool_calls', [])


# ─── MyanAI Agent System Prompts ───────────────────────────────────────────────

MYANAI_SYSTEM_PROMPT = """MyanAi သည် မြန်မာ Web OS (MyanOS) ရဲ့ AI Agent ဖြစ်ပါတယ်။
ပရော်ကိုင်ချက်များ:
- မြန်မာဘာသာနှင့် English နှစ်ခုလုံး ပြောဆိုနိုင်ပါတယ်
- မေးခွန်းတွေကို ကြိုတင်ပြီး အဖြေပေးပါ
- Myanmar programming language (MMR) မှာ ကူညီပေးနိုင်ပါတယ်
- Python, JavaScript, HTML/CSS code တွေ ရေးသားပေးနိုင်ပါတယ်
- Code debugging နှင့် အကြံပြုချက်တွေ ပေးနိုင်ပါတယ်
- ဖြေကြားလျှင် မြန်မာလို ဖြေပေးပါ၊ ရှေ့ပါ English ဖြေပေးပါ
- အကဲဖြတ်စွာနှင့် အသေးစိတ်သာ ဖြေပါ"""

CODE_EXPERT_PROMPT = """You are an expert Python code assistant for MyanOS AI Training Center.
Help users with:
- Writing and debugging Python code
- Machine learning and AI model training
- Data analysis and visualization with matplotlib
- Myanmar NLP tasks
Provide clean, well-commented code. Explain errors clearly."""

CODE_GENERATION_PROMPT = """You are a Python code generation expert for MyanOS.
When given a user query, generate Python code cells that solve the problem.
Return ONLY valid JSON in this exact format:
{
  "cells": [
    {"code": "# First cell code", "description": "What this cell does"},
    {"code": "# Second cell code", "description": "What this cell does"}
  ],
  "explanation": "Overall explanation of the solution"
}
Rules:
- Generate 1-3 cells maximum
- Each cell should be self-contained and executable
- Include helpful comments
- Return ONLY the JSON, no markdown or extra text"""


# ─── Self-Test ──────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print("MyanOS AI Module — Self Test")
    print(f"API URL: {FORGE_API_URL}")
    print(f"API Key: {'configured' if FORGE_API_KEY else 'NOT CONFIGURED'}")
    print(f"Model: {DEFAULT_MODEL}")
    if not FORGE_API_KEY:
        print("\nSet FORGE_API_KEY environment variable to test.")
    else:
        print("\nTesting simple chat...")
        try:
            result = chat_simple("You are a helpful assistant.", "Say hello in Burmese.")
            print(f"Response: {result[:200]}")
            print("OK!")
        except Exception as e:
            print(f"Error: {e}")
