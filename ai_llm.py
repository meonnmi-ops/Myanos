#!/usr/bin/env python3
"""
MyanOS — AI/LLM Integration Module (FREE / LOCAL ONLY)
100% ကျွန်ုပ်တို့ဘာသာ, ခွဲခြမ်းစိတ်ဖြာ API key မလိုပါ

Backends (auto-fallback):
  1. Ollama (local) — offline, 100% free, best for privacy
  2. HuggingFace Inference API (free tier) — cloud, no cost
  3. Groq Free API (free tier) — fast cloud inference

Architecture:
  Ollama available → use Ollama (local)
  Ollama unavailable → try HuggingFace (free cloud)
  HF unavailable   → try Groq (free cloud)
  All unavailable  → graceful error with setup instructions

Features:
  - Chat completions with conversation history
  - Automatic backend fallback
  - Myanmar/English bilingual support
  - Model list management
  - Health check endpoint
"""

import json
import urllib.request
import urllib.error
import os
import time
import subprocess
import sys
import logging

logger = logging.getLogger('myanos.ai')

# ─── Config ────────────────────────────────────────────────────────────────────

# Ollama (local, free, offline)
OLLAMA_BASE_URL = os.environ.get('OLLAMA_BASE_URL', 'http://localhost:11434')
OLLAMA_DEFAULT_MODEL = os.environ.get('OLLAMA_MODEL', 'myanmar-seallm')  # Myanmar SeaLLM (best for Burmese)
OLLAMA_FALLBACK_MODEL = 'llama3.2'  # Fallback if Myanmar model not installed

# HuggingFace Inference API (free tier, no cost)
HF_API_URL = 'https://api-inference.huggingface.co/models/'
HF_TOKEN = os.environ.get('HF_TOKEN', '')  # Optional: increases rate limits
HF_DEFAULT_MODEL = os.environ.get('HF_MODEL', 'Qwen/Qwen2.5-3B-Instruct')

# Groq Free API (fast, free tier)
GROQ_API_URL = os.environ.get('GROQ_API_URL', 'https://api.groq.com/openai/v1/chat/completions')
GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')
GROQ_DEFAULT_MODEL = os.environ.get('GROQ_MODEL', 'llama-3.3-70b-versatile')

# Fallback chain order
BACKEND_PRIORITY = ['ollama', 'huggingface', 'groq']

# Response limits
MAX_TOKENS = 4096
CHAT_TIMEOUT = 90  # seconds


# ═══════════════════════════════════════════════════════════════════════════════
#  OLLAMA BACKEND (Local, Free, Offline)
# ═══════════════════════════════════════════════════════════════════════════════

def _ollama_is_available():
    """Check if Ollama server is running locally."""
    try:
        req = urllib.request.Request(f'{OLLAMA_BASE_URL}/api/tags', method='GET')
        resp = urllib.request.urlopen(req, timeout=3)
        resp.read()
        return True
    except Exception:
        return False


def _ollama_chat(messages, model=None, timeout=CHAT_TIMEOUT):
    """
    Chat with Ollama (local LLM server).
    No API key needed. Works completely offline.

    Args:
        messages: List of dicts with 'role' and 'content' keys
        model: Model name (default: llama3.2)
        timeout: Request timeout in seconds

    Returns:
        dict: {'backend': 'ollama', 'model': str, 'content': str, 'usage': dict}
    """
    model = model or OLLAMA_DEFAULT_MODEL

    # Build Ollama-compatible messages
    ollama_messages = []
    for msg in messages:
        role = msg.get('role', 'user')
        content = msg.get('content', '')
        if isinstance(content, list):
            # Flatten multimodal content
            parts = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    parts.append(item.get('text', json.dumps(item)))
            content = '\n'.join(parts)
        ollama_messages.append({'role': role, 'content': str(content)})

    payload = {
        'model': model,
        'messages': ollama_messages,
        'stream': False,
        'options': {
            'num_predict': MAX_TOKENS,
            'temperature': 0.7,
        }
    }

    req_data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        f'{OLLAMA_BASE_URL}/api/chat',
        data=req_data,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )

    resp = urllib.request.urlopen(req, timeout=timeout)
    body = json.loads(resp.read().decode('utf-8'))

    content = body.get('message', {}).get('content', '')
    usage = {
        'prompt_tokens': body.get('prompt_eval_count', 0),
        'completion_tokens': body.get('eval_count', 0),
        'total_tokens': body.get('prompt_eval_count', 0) + body.get('eval_count', 0),
    }

    return {
        'backend': 'ollama',
        'model': model,
        'content': content,
        'usage': usage,
    }


def _ollama_list_models():
    """List available Ollama models."""
    try:
        req = urllib.request.Request(f'{OLLAMA_BASE_URL}/api/tags', method='GET')
        resp = urllib.request.urlopen(req, timeout=5)
        body = json.loads(resp.read().decode('utf-8'))
        models = body.get('models', [])
        return [{'name': m.get('name', ''), 'size': m.get('size', 0)} for m in models]
    except Exception:
        return []


def _ollama_pull_model(model_name, timeout=300):
    """Download/pull an Ollama model."""
    payload = {'name': model_name, 'stream': False}
    req_data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        f'{OLLAMA_BASE_URL}/api/pull',
        data=req_data,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    resp = urllib.request.urlopen(req, timeout=timeout)
    body = json.loads(resp.read().decode('utf-8'))
    return body.get('status', 'success')


# ═══════════════════════════════════════════════════════════════════════════════
#  HUGGINGFACE BACKEND (Free Tier, Cloud)
# ═══════════════════════════════════════════════════════════════════════════════

def _hf_is_available():
    """Check if HuggingFace Inference API is accessible."""
    # HF Inference API works without token for popular models (with rate limits)
    return True  # Always available (may be rate-limited without token)


def _hf_chat(messages, model=None, timeout=CHAT_TIMEOUT):
    """
    Chat with HuggingFace Inference API (free tier).
    Works without API token but with lower rate limits.

    Args:
        messages: List of dicts with 'role' and 'content' keys
        model: HF model name (default: microsoft/phi-4-mini-instruct)
        timeout: Request timeout in seconds

    Returns:
        dict: {'backend': 'huggingface', 'model': str, 'content': str, 'usage': dict}
    """
    model = model or HF_DEFAULT_MODEL

    # Build a single prompt from messages (HF text-generation inference)
    prompt_parts = []
    for msg in messages:
        role = msg.get('role', 'user')
        content = msg.get('content', '')
        if isinstance(content, list):
            parts = [item.get('text', str(item)) if isinstance(item, dict) else str(item)
                     for item in content]
            content = '\n'.join(parts)
        if role == 'system':
            prompt_parts.append(f'System: {content}')
        elif role == 'assistant':
            prompt_parts.append(f'Assistant: {content}')
        else:
            prompt_parts.append(f'User: {content}')
    prompt_parts.append('Assistant:')

    prompt = '\n'.join(prompt_parts)

    # Try conversational endpoint first, fall back to text-generation
    # Conversational endpoint
    conv_payload = {
        'model': model,
        'messages': messages,
        'max_tokens': MAX_TOKENS,
        'temperature': 0.7,
    }

    headers = {'Content-Type': 'application/json'}
    if HF_TOKEN:
        headers['Authorization'] = f'Bearer {HF_TOKEN}'

    # Try /v1/chat/completions (OpenAI-compatible)
    try:
        req_data = json.dumps(conv_payload).encode('utf-8')
        req = urllib.request.Request(
            f'{HF_API_URL}{model}/v1/chat/completions',
            data=req_data,
            headers=headers,
            method='POST',
        )
        resp = urllib.request.urlopen(req, timeout=timeout)
        body = json.loads(resp.read().decode('utf-8'))
        content = body.get('choices', [{}])[0].get('message', {}).get('content', '')
        usage = body.get('usage', {})
        return {
            'backend': 'huggingface',
            'model': model,
            'content': content,
            'usage': usage,
        }
    except urllib.error.HTTPError:
        pass

    # Fallback: standard inference endpoint
    std_payload = {
        'inputs': prompt,
        'parameters': {
            'max_new_tokens': MAX_TOKENS,
            'temperature': 0.7,
            'return_full_text': False,
        }
    }
    req_data = json.dumps(std_payload).encode('utf-8')
    req = urllib.request.Request(
        f'{HF_API_URL}{model}',
        data=req_data,
        headers=headers,
        method='POST',
    )
    resp = urllib.request.urlopen(req, timeout=timeout)
    body = json.loads(resp.read().decode('utf-8'))

    # Parse response (may be array or dict)
    if isinstance(body, list):
        content = body[0].get('generated_text', '')
    elif isinstance(body, dict):
        content = body.get('generated_text', '')
    else:
        content = str(body)

    return {
        'backend': 'huggingface',
        'model': model,
        'content': content,
        'usage': {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0},
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  GROQ BACKEND (Free Tier, Cloud, Fast)
# ═══════════════════════════════════════════════════════════════════════════════

def _groq_is_available():
    """Check if Groq API key is configured."""
    return bool(GROQ_API_KEY)


def _groq_chat(messages, model=None, timeout=CHAT_TIMEOUT):
    """
    Chat with Groq API (free tier).
    Requires free API key from https://console.groq.com

    Args:
        messages: List of dicts with 'role' and 'content' keys
        model: Model name (default: llama-3.3-70b-versatile)
        timeout: Request timeout in seconds

    Returns:
        dict: {'backend': 'groq', 'model': str, 'content': str, 'usage': dict}
    """
    model = model or GROQ_DEFAULT_MODEL

    payload = {
        'model': model,
        'messages': messages,
        'max_tokens': MAX_TOKENS,
        'temperature': 0.7,
    }

    req_data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        GROQ_API_URL,
        data=req_data,
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {GROQ_API_KEY}',
        },
        method='POST',
    )

    resp = urllib.request.urlopen(req, timeout=timeout)
    body = json.loads(resp.read().decode('utf-8'))

    content = body.get('choices', [{}])[0].get('message', {}).get('content', '')
    usage = body.get('usage', {})

    return {
        'backend': 'groq',
        'model': model,
        'content': content,
        'usage': usage,
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  UNIFIED INTERFACE (Auto-Fallback)
# ═══════════════════════════════════════════════════════════════════════════════

# Backend registry
_BACKENDS = {
    'ollama': {
        'is_available': _ollama_is_available,
        'chat': _ollama_chat,
        'list_models': _ollama_list_models,
    },
    'huggingface': {
        'is_available': _hf_is_available,
        'chat': _hf_chat,
        'list_models': lambda: [],
    },
    'groq': {
        'is_available': _groq_is_available,
        'chat': _groq_chat,
        'list_models': lambda: [],
    },
}

# Cache availability status (refreshed on each call)
_availability_cache = {}
_cache_time = 0
CACHE_TTL = 30  # seconds


def _check_backend_status(backend_name):
    """Check if a backend is available, with caching."""
    global _availability_cache, _cache_time
    now = time.time()

    if now - _cache_time > CACHE_TTL:
        _availability_cache = {}
        _cache_time = now

    if backend_name not in _availability_cache:
        try:
            _availability_cache[backend_name] = _BACKENDS[backend_name]['is_available']()
        except Exception:
            _availability_cache[backend_name] = False

    return _availability_cache[backend_name]


def get_active_backend():
    """
    Find the first available backend in priority order.
    Returns: (backend_name, backend_info) or (None, None)
    """
    for name in BACKEND_PRIORITY:
        if _check_backend_status(name):
            return name, _BACKENDS[name]
    return None, None


def get_all_backend_status():
    """Get status of all backends, including which Ollama model is loaded."""
    status = {}
    for name in BACKEND_PRIORITY:
        model_name = {
            'ollama': OLLAMA_DEFAULT_MODEL,
            'huggingface': HF_DEFAULT_MODEL,
            'groq': GROQ_DEFAULT_MODEL,
        }.get(name, '')

        # For Ollama, check if Myanmar model is actually installed
        if name == 'ollama' and _check_backend_status('ollama'):
            try:
                installed = _ollama_list_models()
                installed_names = [m['name'] for m in installed]
                if OLLAMA_DEFAULT_MODEL not in installed_names and OLLAMA_FALLBACK_MODEL in installed_names:
                    model_name = f'{OLLAMA_DEFAULT_MODEL} (not found, fallback: {OLLAMA_FALLBACK_MODEL})'
            except Exception:
                pass

        status[name] = {
            'available': _check_backend_status(name),
            'model': model_name,
        }
    return status


def chat(messages, backend=None, model=None, timeout=CHAT_TIMEOUT):
    """
    Send a chat completion request — auto-selects best available backend.

    Priority: Ollama (local) > HuggingFace (free cloud) > Groq (free cloud)

    Args:
        messages: List of dicts with 'role' and 'content' keys
        backend: Force specific backend ('ollama', 'huggingface', 'groq', or None for auto)
        model: Override model name (None = use backend default)
        timeout: Request timeout in seconds

    Returns:
        dict: {
            'success': True/False,
            'backend': str,
            'model': str,
            'content': str,
            'usage': dict,
            'error': str (on failure)
        }
    """
    # If specific backend requested, try only that one
    if backend and backend in _BACKENDS:
        try:
            result = _BACKENDS[backend]['chat'](messages, model=model, timeout=timeout)
            return {'success': True, **result}
        except Exception as e:
            return {
                'success': False,
                'backend': backend,
                'model': model or 'unknown',
                'content': '',
                'usage': {},
                'error': f'{backend} error: {str(e)}',
            }

    # Auto-fallback: try each backend in priority order
    errors = []
    for name in BACKEND_PRIORITY:
        try:
            if not _check_backend_status(name):
                errors.append(f'{name}: not available')
                continue

            result = _BACKENDS[name]['chat'](messages, model=model, timeout=timeout)
            logger.info(f'AI response from {name} ({result.get("model", "?")})')
            return {'success': True, **result}

        except Exception as e:
            errors.append(f'{name}: {str(e)}')
            logger.warning(f'Backend {name} failed: {e}')
            # Invalidate cache for this backend
            _availability_cache.pop(name, None)
            continue

    # All backends failed
    return {
        'success': False,
        'backend': 'none',
        'model': 'none',
        'content': '',
        'usage': {},
        'error': 'All AI backends unavailable.\n\n'
                 'Setup guide:\n'
                 '1. Ollama (local, free): Install from https://ollama.com then run: ollama pull llama3.2\n'
                 '2. HuggingFace (free cloud): Set HF_TOKEN env var for higher rate limits\n'
                 '3. Groq (free cloud): Get free key from https://console.groq.com, set GROQ_API_KEY\n'
                 f'\nTried: {"; ".join(errors)}',
    }


# ─── Helper Functions ──────────────────────────────────────────────────────────

def chat_simple(system_prompt, user_message, backend=None, model=None):
    """Simple one-shot chat without conversation history."""
    return chat(
        messages=[
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_message},
        ],
        backend=backend,
        model=model,
    )


def chat_with_history(messages, backend=None, model=None):
    """Chat with full conversation history."""
    return chat(messages=messages, backend=backend, model=model)


def list_available_models():
    """List all available models across all backends."""
    all_models = []

    # Ollama models (local)
    if _check_backend_status('ollama'):
        try:
            ollama_models = _ollama_list_models()
            for m in ollama_models:
                all_models.append({
                    'backend': 'ollama',
                    'name': m['name'],
                    'local': True,
                    'size': m.get('size', 0),
                })
        except Exception:
            pass

    # HuggingFace models (suggested free models)
    hf_free_models = [
        'microsoft/phi-4-mini-instruct',
        'HuggingFaceH4/zephyr-7b-beta',
        'mistralai/Mistral-7B-Instruct-v0.3',
        'google/gemma-3-4b-it',
        'meta-llama/Llama-3.2-3B-Instruct',
    ]
    for m in hf_free_models:
        all_models.append({
            'backend': 'huggingface',
            'name': m,
            'local': False,
        })

    # Groq models
    if _check_backend_status('groq'):
        groq_models = [
            'llama-3.3-70b-versatile',
            'llama-3.1-8b-instant',
            'gemma2-9b-it',
            'mixtral-8x7b-32768',
        ]
        for m in groq_models:
            all_models.append({
                'backend': 'groq',
                'name': m,
                'local': False,
            })

    return all_models


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
    print("=" * 50)
    print("MyanOS AI Module — Self Test (FREE / LOCAL)")
    print("=" * 50)

    # Check all backends
    print("\n--- Backend Status ---")
    status = get_all_backend_status()
    for name, info in status.items():
        icon = '✅' if info['available'] else '❌'
        print(f"  {icon} {name}: model={info['model']}")

    # List models
    print("\n--- Available Models ---")
    models = list_available_models()
    for m in models:
        loc = '(local)' if m.get('local') else '(cloud)'
        print(f"  • [{m['backend']}]{loc} {m['name']}")

    # Test chat
    active = get_active_backend()
    print(f"\n--- Active Backend: {active[0] or 'NONE'} ---")

    if active[0]:
        print("\nTesting chat...")
        result = chat_simple(
            "You are a helpful assistant. Respond in Burmese.",
            "မင်္ဂလာပါ။ သင်ကဘာကိုနိုင်ပါလဲး။ 2+2=အမျိုးမှန်းဖြေပါ။"
        )
        print(f"  Success: {result['success']}")
        print(f"  Backend: {result['backend']}")
        print(f"  Model:   {result['model']}")
        print(f"  Content: {result['content'][:200]}")
        print(f"  Usage:   {result.get('usage', {})}")
    else:
        print("\nNo AI backend available.")
        print("Install Ollama: https://ollama.com")
        print("  then: ollama pull llama3.2")
        print("Or set GROQ_API_KEY env var for free cloud AI.")
