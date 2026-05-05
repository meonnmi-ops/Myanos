#!/usr/bin/env python3
"""
MMR Shell v1.0.0 — Myanmar's Real Shell
Author: Meonnmi-ops | Myanos Web OS

Real shell with:
  - Built-in commands (cd, pwd, ls, cat, mkdir, rm, cp, mv, echo, clear, help...)
  - myan package manager (install, remove, list, search, info, update, upgrade)
  - Python exec (python3)
  - Myanmar Code exec (mmc)
  - Pipe to real system commands (apt, pacman, pkg, git, pip, npm)
  - neofetch, whoami, uname, date, env, export, alias, history

Usage:
  from shell import MMRShell
  shell = MMRShell()
  output, status = shell.execute("myan list")
"""

import os
import sys
import subprocess
import platform
import json
import shutil
import signal
import glob as globmod
from pathlib import Path
from datetime import datetime

# ─── Globals ────────────────────────────────────────────────────────────────
VERSION = "1.0.0"
BASE_DIR = Path(__file__).parent
HOME = Path.home()
CWD = [Path.cwd()]  # mutable for cd
HISTORY = []
HISTORY_FILE = BASE_DIR / ".mmr_history"
MAX_HISTORY = 500

# ─── ANSI Colors ────────────────────────────────────────────────────────────
class C:
    R = '\033[0;31m'
    G = '\033[0;32m'
    Y = '\033[1;33m'
    B = '\033[0;34m'
    M = '\033[0;35m'
    C = '\033[0;36m'
    W = '\033[1;37m'
    D = '\033[2m'
    BD = '\033[1m'
    NC = '\033[0m'

# ─── Banner ─────────────────────────────────────────────────────────────────
BANNER = f"""{C.B}
       ┌──────────────┐
       │   Myanos OS   │
       │  ████████████  │
       │  █▀▀▀▀▀▀▀▀█  │
       │  █ ▀▀▀▀▀▀ █  │
       │    ▀▀▀▀▀▀    │
       └──────────────┘{C.NC}
  {C.C}MMR Shell v{VERSION}{C.NC} — Myanmar's Real Shell
  {C.D}Type 'help' for commands | 'myan help' for package manager{C.NC}
"""

PROMPT = f"{C.G}meonnmi{C.NC}@{C.B}myanos{C.NC}:{C.C}~{C.NC}$ "


class MMRShell:
    """MMR Shell — real shell for Myanos Web OS"""

    def __init__(self, session=None):
        self.cwd = CWD[0]
        self.session = session
        self.aliases = {
            'll': 'ls -la',
            'la': 'ls -a',
            'cls': 'clear',
            'q': 'exit',
            'neof': 'neofetch',
            '..': 'cd ..',
        }
        self.env = {
            'HOME': str(HOME),
            'MYANOS_DIR': str(BASE_DIR),
            'MYANOS_VERSION': '2.1.0',
            'SHELL': 'mmr',
            'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
        }
        # Load history
        self._load_history()

    def execute(self, cmd_str):
        """
        Execute a command and return (output_string, exit_status).
        This is the main entry point called by server.py API.
        """
        cmd_str = cmd_str.strip()
        if not cmd_str:
            return ('', 0)

        # Add to history
        self._add_history(cmd_str)

        # Handle pipes and chains
        if '|' in cmd_str:
            return self._handle_pipe(cmd_str)
        if '&&' in cmd_str:
            return self._handle_chain(cmd_str, '&&')
        if '||' in cmd_str:
            return self._handle_chain(cmd_str, '||')
        if ';' in cmd_str and ';;' not in cmd_str:
            return self._handle_semicolon(cmd_str)

        # Parse command
        parts = self._parse_cmd(cmd_str)
        if not parts:
            return ('', 0)

        name = parts[0]
        args = parts[1:]

        # Built-in commands
        builtins = {
            'exit': self._cmd_exit,
            'help': self._cmd_help,
            'clear': self._cmd_clear,
            'cd': self._cmd_cd,
            'pwd': self._cmd_pwd,
            'ls': self._cmd_ls,
            'cat': self._cmd_cat,
            'mkdir': self._cmd_mkdir,
            'rmdir': self._cmd_rmdir,
            'rm': self._cmd_rm,
            'cp': self._cmd_cp,
            'mv': self._cmd_mv,
            'touch': self._cmd_touch,
            'echo': self._cmd_echo,
            'head': self._cmd_head,
            'tail': self._cmd_tail,
            'wc': self._cmd_wc,
            'grep': self._cmd_grep,
            'find': self._cmd_find,
            'which': self._cmd_which,
            'whoami': self._cmd_whoami,
            'hostname': self._cmd_hostname,
            'uname': self._cmd_uname,
            'date': self._cmd_date,
            'env': self._cmd_env,
            'export': self._cmd_export,
            'alias': self._cmd_alias,
            'history': self._cmd_history,
            'neofetch': self._cmd_neofetch,
            'df': self._cmd_df,
            'du': self._cmd_du,
            'free': self._cmd_free,
            'uptime': self._cmd_uptime,
            'ps': self._cmd_ps,
            'kill': self._cmd_kill,
            'chmod': self._cmd_chmod,
            'wget': self._cmd_wget,
            'curl': self._cmd_curl,
            'python3': self._cmd_python,
            'python': self._cmd_python,
            'pip': self._cmd_pip,
            'pip3': self._cmd_pip,
            'git': self._cmd_git,
            'npm': self._cmd_npm,
            'node': self._cmd_node,
            'mmr': lambda a: (f"{C.C}MMR Shell v{VERSION}{C.NC}\nMyanmar's Real Shell\nType 'help' for commands", 0),
            'myan': self._cmd_myan,
            'mmc': self._cmd_mmc,
        }

        # Check alias
        if name in self.aliases:
            expanded = self.aliases[name] + ' ' + ' '.join(args)
            return self.execute(expanded)

        # Check builtin
        if name in builtins:
            try:
                result = builtins[name](args)
                if isinstance(result, tuple):
                    return result
                return (str(result), 0)
            except SystemExit:
                return ('exit', 0)
            except Exception as e:
                return (f'{C.R}[ERR] {e}{C.NC}', 1)

        # Try system command
        return self._exec_system(parts)

    # ─── Command Parser ────────────────────────────────────────────────────
    def _parse_cmd(self, cmd_str):
        """Parse command string into parts, respecting quotes"""
        parts = []
        current = ''
        in_quote = None
        escape = False

        for ch in cmd_str:
            if escape:
                current += ch
                escape = False
            elif ch == '\\':
                escape = True
            elif ch in ('"', "'") and in_quote is None:
                in_quote = ch
            elif ch == in_quote:
                in_quote = None
            elif ch == ' ' and in_quote is None:
                if current:
                    parts.append(current)
                    current = ''
            else:
                current += ch

        if current:
            parts.append(current)
        return parts

    def _resolve_path(self, path):
        """Resolve a path relative to current working directory"""
        if path.startswith('~'):
            path = str(HOME) + path[1:]
        elif path.startswith('/'):
            pass
        else:
            path = str(self.cwd) + '/' + path
        return os.path.normpath(path)

    # ─── Pipe / Chain Handlers ─────────────────────────────────────────────
    def _handle_pipe(self, cmd_str):
        cmds = cmd_str.split('|')
        prev_output = ''
        for cmd in cmds:
            cmd = cmd.strip()
            if prev_output:
                # Append prev output as arg
                full_cmd = f"{cmd} {prev_output}"
            else:
                full_cmd = cmd
            out, status = self.execute(full_cmd)
            prev_output = out
            if status != 0 and prev_output:
                break
        return (prev_output, 0)

    def _handle_chain(self, cmd_str, operator):
        if operator == '&&':
            cmds = cmd_str.split('&&')
            last_out = ''
            for cmd in cmds:
                cmd = cmd.strip()
                if not cmd:
                    continue
                out, status = self.execute(cmd)
                last_out = out
                if status != 0:
                    return (out, status)
            return (last_out, 0)
        else:  # ||
            cmds = cmd_str.split('||')
            last_out = ''
            last_status = 1
            for cmd in cmds:
                cmd = cmd.strip()
                if not cmd:
                    continue
                out, status = self.execute(cmd)
                last_out = out
                last_status = status
                if status == 0:
                    return (out, 0)
            return (last_out, last_status)

    def _handle_semicolon(self, cmd_str):
        cmds = cmd_str.split(';')
        last_out = ''
        last_status = 0
        for cmd in cmds:
            cmd = cmd.strip()
            if not cmd:
                continue
            out, status = self.execute(cmd)
            last_out = out
            last_status = status
        return (last_out, last_status)

    # ─── System Command Executor ───────────────────────────────────────────
    def _exec_system(self, parts):
        """Execute a real system command"""
        cmd = parts[0]
        args = parts[1:]

        # Security: block dangerous commands
        blocked = ['rm', '-rf', '/']
        if cmd == 'rm' and '/' in args and '-rf' in args:
            return (f'{C.R}[BLOCKED] rm -rf / is not allowed{C.NC}', 1)

        try:
            result = subprocess.run(
                parts,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(self.cwd),
                env={**os.environ, **self.env},
            )
            output = result.stdout + result.stderr
            if not output.strip():
                output = ''
            return (output, result.returncode)
        except FileNotFoundError:
            return (f'{C.R}[ERR] Command not found: {cmd}{C.NC}\n{C.D}Type "help" for available commands{C.NC}', 1)
        except subprocess.TimeoutExpired:
            return (f'{C.R}[ERR] Command timed out: {cmd}{C.NC}', 1)
        except Exception as e:
            return (f'{C.R}[ERR] {e}{C.NC}', 1)

    # ─── Built-in Commands ─────────────────────────────────────────────────

    def _cmd_exit(self, args):
        return ('exit', 0)

    def _cmd_help(self, args):
        h = f"""{C.BD}MMR Shell v{VERSION} — Commands{C.NC}

{C.Y}Navigation:{C.NC}
  cd [path]         Change directory
  pwd               Print working directory
  ls [path]         List files (flags: -l, -a, -la, -R)
  find [path] [expr] Find files
  which [cmd]       Locate command

{C.Y}File Operations:{C.NC}
  cat [file]        Print file content
  head [file]       First 10 lines
  tail [file]       Last 10 lines
  touch [file]      Create empty file
  mkdir [dir]       Create directory
  rmdir [dir]       Remove empty directory
  rm [file]         Remove file/dir
  cp [src] [dst]    Copy file
  mv [src] [dst]    Move/rename file
  grep [pat] [file] Search in file
  wc [file]         Word/line/char count

{C.Y}System:{C.NC}
  whoami            Current user
  hostname          System hostname
  uname [-a]        System info
  date              Current date/time
  neofetch          System info (fancy)
  df                Disk usage
  du [path]         Directory size
  free              Memory usage
  uptime            System uptime
  ps                Process list
  kill [pid]        Kill process
  env               Environment variables
  export K=V        Set environment variable
  chmod [mode] [f]  Change permissions

{C.Y}Network:{C.NC}
  wget [url]        Download file
  curl [url]        HTTP request
  ping [host]       Ping host

{C.Y}Development:{C.NC}
  python3 [file]    Run Python script
  pip [cmd]         Python package manager
  git [cmd]         Git version control
  npm [cmd]         Node package manager
  node [file]       Run Node.js script
  mmc [code]        Myanmar Code execution

{C.Y}Myanos:{C.NC}
  myan [cmd]        📦 Myan Package Manager
  myan list         List installed packages
  myan install [f]  Install .myan package
  myan remove [n]   Remove package
  myan search [q]   Search packages
  myan info [n]     Package details
  myan update       Update package list
  myan upgrade      Upgrade all packages

{C.Y}Shell:{C.NC}
  alias [n]=[v]     Create alias
  history           Command history
  clear             Clear screen
  exit              Exit shell

{C.Y}Chains & Pipes:{C.NC}
  cmd1 && cmd2      Run if cmd1 succeeds
  cmd1 || cmd2      Run if cmd1 fails
  cmd1 ; cmd2       Run both
  cmd1 | cmd2       Pipe output

{C.D}Tip: All real system commands (apt, pacman, pkg, git, etc.) work too!{C.NC}"""
        return (h, 0)

    def _cmd_clear(self, args):
        return ('__CLEAR__', 0)

    def _cmd_cd(self, args):
        if not args or args[0] == '~':
            target = HOME
        elif args[0] == '-':
            target = self.cwd  # No prev dir tracking in API mode
        else:
            target = self._resolve_path(args[0])

        if os.path.isdir(target):
            self.cwd = Path(target)
            CWD[0] = self.cwd
            return ('', 0)
        else:
            return (f'{C.R}[ERR] No such directory: {args[0]}{C.NC}', 1)

    def _cmd_pwd(self, args):
        return (str(self.cwd), 0)

    def _cmd_ls(self, args):
        target = '.'
        flags = set()
        for a in args:
            if a.startswith('-'):
                flags.update(a[1:])
            else:
                target = a

        path = self._resolve_path(target)
        if not os.path.isdir(path):
            return (f'{C.R}[ERR] Not a directory: {target}{C.NC}', 1)

        try:
            entries = sorted(os.listdir(path))
            show_all = 'a' in flags
            show_long = 'l' in flags
            show_recursive = 'R' in flags

            if show_all:
                entries = ['.', '..'] + entries

            # Filter hidden unless -a
            if not show_all:
                entries = [e for e in entries if not e.startswith('.')]

            if show_recursive:
                return self._ls_recursive(path, entries, show_long, show_all)

            if show_long:
                lines = []
                for e in entries:
                    full = os.path.join(path, e)
                    if os.path.isdir(full):
                        lines.append(f"{C.B}{e}/{C.NC}")
                    elif os.path.islink(full):
                        lines.append(f"{C.C}{e}@{C.NC}")
                    elif os.access(full, os.X_OK):
                        lines.append(f"{C.G}{e}*{C.NC}")
                    else:
                        lines.append(e)
                return ('\n'.join(lines), 0)
            else:
                items = []
                for e in entries:
                    full = os.path.join(path, e)
                    if os.path.isdir(full):
                        items.append(f"{C.B}{e}/{C.NC}")
                    else:
                        items.append(e)
                return ('  '.join(items), 0)
        except PermissionError:
            return (f'{C.R}[ERR] Permission denied: {path}{C.NC}', 1)

    def _ls_recursive(self, path, entries, show_long, show_all):
        lines = [f"{C.BD}{path}:{C.NC}"]
        for e in entries:
            full = os.path.join(path, e)
            if os.path.isdir(full):
                lines.append(f"{C.B}{e}/{C.NC}")
                try:
                    sub_entries = sorted(os.listdir(full))
                    if not show_all:
                        sub_entries = [s for s in sub_entries if not s.startswith('.')]
                    sub_lines = [f"{C.BD}{full}:{C.NC}"]
                    for s in sub_entries:
                        sf = os.path.join(full, s)
                        if os.path.isdir(sf):
                            sub_lines.append(f"{C.B}{s}/{C.NC}")
                        else:
                            sub_lines.append(s)
                    lines.append('\n'.join(sub_lines))
                except PermissionError:
                    lines.append(f"{C.R}Permission denied{C.NC}")
            else:
                lines.append(e)
        return ('\n'.join(lines), 0)

    def _cmd_cat(self, args):
        if not args:
            return (f'{C.R}[ERR] Usage: cat [file]{C.NC}', 1)
        outputs = []
        for a in args:
            path = self._resolve_path(a)
            if not os.path.isfile(path):
                outputs.append(f'{C.R}[ERR] No such file: {a}{C.NC}')
                continue
            try:
                with open(path, 'r', errors='replace') as f:
                    outputs.append(f.read())
            except PermissionError:
                outputs.append(f'{C.R}[ERR] Permission denied: {a}{C.NC}')
        return ('\n'.join(outputs), 0)

    def _cmd_head(self, args):
        n = 10
        files = []
        for a in args:
            if a.startswith('-n'):
                try: n = int(a[2:]) if len(a) > 2 else int(args[args.index(a)+1])
                except: pass
            elif not a.startswith('-'):
                files.append(a)
        if not files:
            return (f'{C.R}[ERR] Usage: head [-n N] [file]{C.NC}', 1)
        outputs = []
        for f in files:
            path = self._resolve_path(f)
            if os.path.isfile(path):
                with open(path, 'r', errors='replace') as fh:
                    lines = [next(fh, '') for _ in range(n)]
                    outputs.append(''.join(lines))
        return ('\n'.join(outputs), 0)

    def _cmd_tail(self, args):
        n = 10
        files = []
        for a in args:
            if a.startswith('-n'):
                try: n = int(a[2:]) if len(a) > 2 else int(args[args.index(a)+1])
                except: pass
            elif not a.startswith('-'):
                files.append(a)
        if not files:
            return (f'{C.R}[ERR] Usage: tail [-n N] [file]{C.NC}', 1)
        outputs = []
        for f in files:
            path = self._resolve_path(f)
            if os.path.isfile(path):
                with open(path, 'r', errors='replace') as fh:
                    lines = fh.readlines()
                    outputs.append(''.join(lines[-n:]))
        return ('\n'.join(outputs), 0)

    def _cmd_wc(self, args):
        if not args:
            return (f'{C.R}[ERR] Usage: wc [file]{C.NC}', 1)
        results = []
        for a in args:
            path = self._resolve_path(a)
            if os.path.isfile(path):
                with open(path, 'r', errors='replace') as f:
                    content = f.read()
                lines = len(content.splitlines())
                words = len(content.split())
                chars = len(content)
                results.append(f'  {lines:>6} {words:>6} {chars:>6} {a}')
        return ('\n'.join(results), 0)

    def _cmd_grep(self, args):
        if len(args) < 2:
            return (f'{C.R}[ERR] Usage: grep [pattern] [file]{C.NC}', 1)
        pattern = args[0]
        path = self._resolve_path(args[1])
        if not os.path.isfile(path):
            return (f'{C.R}[ERR] No such file: {args[1]}{C.NC}', 1)
        try:
            with open(path, 'r', errors='replace') as f:
                lines = f.readlines()
            matches = []
            for i, line in enumerate(lines, 1):
                if pattern in line:
                    # Highlight match
                    highlighted = line.replace(pattern, f'{C.R}{pattern}{C.NC}')
                    matches.append(f'{C.D}{i}:{C.NC}{highlighted.rstrip()}')
            if not matches:
                return (f'{C.D}(no matches){C.NC}', 0)
            return ('\n'.join(matches), 0)
        except Exception as e:
            return (f'{C.R}[ERR] {e}{C.NC}', 1)

    def _cmd_find(self, args):
        start = self._resolve_path(args[0]) if args else str(self.cwd)
        name_pattern = ''
        for i, a in enumerate(args):
            if a == '-name' and i + 1 < len(args):
                name_pattern = args[i + 1]
                break

        if not os.path.isdir(start):
            return (f'{C.R}[ERR] Not a directory: {start}{C.NC}', 1)

        results = []
        try:
            for root, dirs, files in os.walk(start):
                for f in files:
                    if name_pattern:
                        if self._fnmatch(f, name_pattern):
                            results.append(os.path.join(root, f))
                    else:
                        results.append(os.path.join(root, f))
                if len(results) > 200:
                    results.append(f'{C.Y}... (truncated, showing first 200){C.NC}')
                    break
        except PermissionError:
            pass
        return ('\n'.join(results) if results else f'{C.D}(no results){C.NC}', 0)

    def _fnmatch(self, name, pattern):
        """Simple glob matching"""
        import fnmatch
        return fnmatch.fnmatch(name, pattern)

    def _cmd_which(self, args):
        if not args:
            return (f'{C.R}[ERR] Usage: which [command]{C.NC}', 1)
        cmd = args[0]
        # Check builtins
        builtins = ['cd','pwd','ls','cat','mkdir','rm','cp','mv','echo','clear','help','exit','myan','mmr','mmc','neofetch','touch','head','tail','grep','find','wc','which','whoami','hostname','uname','date','env','export','alias','history','df','du','free','uptime','ps','kill','chmod','wget','curl','python3','python','pip','pip3','git','npm','node','rmdir']
        if cmd in builtins:
            return (f'{C.G}{cmd}{C.NC}: mmr built-in command', 0)
        # Check system PATH
        path_dirs = os.environ.get('PATH', '').split(':')
        for d in path_dirs:
            full = os.path.join(d, cmd)
            if os.path.isfile(full) and os.access(full, os.X_OK):
                return (full, 0)
        return (f'{C.R}{cmd} not found{C.NC}', 1)

    def _cmd_whoami(self, args):
        return (os.environ.get('USER', 'meonnmi'), 0)

    def _cmd_hostname(self, args):
        return ('myanos', 0)

    def _cmd_uname(self, args):
        if '-a' in args or '--all' in args:
            return (f'Myanos OS 2.1.0 myanos {platform.system().lower()}-{platform.machine()} Python/{platform.python_version()}', 0)
        return (f'Myanos OS', 0)

    def _cmd_date(self, args):
        if args and ('+%s' in args or '+%s' in ' '.join(args)):
            return (str(int(datetime.now().timestamp())), 0)
        return (datetime.now().strftime('%a %b %d %H:%M:%S %Y'), 0)

    def _cmd_env(self, args):
        lines = []
        env = {**os.environ, **self.env}
        for k in sorted(env.keys()):
            lines.append(f'{k}={env[k]}')
        return ('\n'.join(lines), 0)

    def _cmd_export(self, args):
        for a in args:
            if '=' in a:
                k, v = a.split('=', 1)
                self.env[k.strip()] = v.strip()
                os.environ[k.strip()] = v.strip()
                return (f'{C.D}exported {k.strip()}={v.strip()}{C.NC}', 0)
        return ('', 0)

    def _cmd_alias(self, args):
        if not args:
            lines = [f"ll='ls -la'", f"la='ls -a'", f"cls='clear'", f"neof='neofetch'"]
            for k, v in self.aliases.items():
                if k not in ['ll','la','cls','neof']:
                    lines.append(f"{k}='{v}'")
            return ('\n'.join(lines), 0)
        for a in args:
            if '=' in a:
                k, v = a.split('=', 1)
                self.aliases[k.strip()] = v.strip().strip("'\"")
                return (f'{C.D}alias {k.strip()}=\'{v.strip()}\'{C.NC}', 0)
        return (f'{C.R}[ERR] Usage: alias name=command{C.NC}', 1)

    def _cmd_history(self, args):
        if not HISTORY:
            return (f'{C.D}(no history){C.NC}', 0)
        lines = []
        for i, cmd in enumerate(HISTORY[-50:], 1):
            lines.append(f'{C.D}{i:>4}{C.NC}  {cmd}')
        return ('\n'.join(lines), 0)

    def _cmd_neofetch(self, args):
        db_path = BASE_DIR / '.myan_db.json'
        pkg_count = 0
        if db_path.exists():
            try:
                with open(db_path) as f:
                    db = json.load(f)
                pkg_count = len(db.get('packages', {}))
            except:
                pass

        # Try to get real system info
        cpu_info = 'Unknown'
        mem_info = 'Unknown'
        try:
            result = subprocess.run(['uname', '-m'], capture_output=True, text=True, timeout=5)
            arch = result.stdout.strip()
            cpu_info = f'{arch} CPU'
        except:
            cpu_info = platform.machine()

        try:
            if platform.system() == 'Linux':
                result = subprocess.run(['free', '-h'], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    lines = result.stdout.strip().split('\n')
                    if len(lines) >= 2:
                        mem_parts = lines[1].split()
                        mem_info = f'{mem_parts[1]} / {mem_parts[1]}' if len(mem_parts) > 1 else 'N/A'
        except:
            pass

        return (f"""{C.B}       ┌──────────────┐
       │   Myanos OS   │
       │  ████████████  │
       │  █▀▀▀▀▀▀▀▀█  │
       │  █ ▀▀▀▀▀▀ █  │
       │    ▀▀▀▀▀▀    │
       └──────────────┘{C.NC}
{C.G}meonnmi{C.NC}@{C.B}myanos{C.NC}
{C.D}─────────────────────────────────────{C.NC}
  {C.W}OS:{C.NC}        Myanos Web OS v2.1.0
  {C.W}Host:{C.NC}      myanos
  {C.W}Kernel:{C.NC}    {platform.system()} {platform.release()}
  {C.W}Shell:{C.NC}     mmr v{VERSION}
  {C.W}Terminal:{C.NC}  Myanos Desktop
  {C.W}CPU:{C.NC}       {cpu_info}
  {C.W}Memory:{C.NC}    {mem_info}
  {C.W}Uptime:{C.NC}    {self._get_uptime()}
  {C.W}Packages:{C.NC}  {pkg_count} (.myan)
  {C.W}Language:{C.NC}  Myanmar Code (127 keywords)
  {C.W}Python:{C.NC}    {platform.python_version()}
  {C.W}Disk:{C.NC}      {self._get_disk_info()}
{C.D}─────────────────────────────────────{C.NC}
  {C.B}●{C.NC} {C.Y}●{C.NC} {C.G}●{C.NC} {C.R}●{C.NC} {C.M}●{C.NC} {C.C}●{C.NC} {C.W}●{C.NC} {C.BD}●{C.NC}

  {C.G}🇲🇲 Myanos Web OS — Myanmar's First Advanced Web OS{C.NC}
  {C.D}CTO: Meonnmi-ops | github.com/meonnmi-ops/Myanos{C.NC}""", 0)

    def _get_uptime(self):
        try:
            if platform.system() == 'Linux':
                with open('/proc/uptime') as f:
                    uptime_sec = float(f.read().split()[0])
                h = int(uptime_sec // 3600)
                m = int((uptime_sec % 3600) // 60)
                return f'{h}h {m}m'
        except:
            pass
        return 'N/A'

    def _get_disk_info(self):
        try:
            if platform.system() == 'Linux':
                result = subprocess.run(['df', '-h', '/'], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    lines = result.stdout.strip().split('\n')
                    if len(lines) >= 2:
                        parts = lines[1].split()
                        return f'{parts[2]} / {parts[1]} ({parts[4]})'
        except:
            pass
        return 'N/A'

    def _cmd_echo(self, args):
        return (' '.join(args), 0)

    def _cmd_touch(self, args):
        if not args:
            return (f'{C.R}[ERR] Usage: touch [file]{C.NC}', 1)
        results = []
        for a in args:
            path = self._resolve_path(a)
            try:
                Path(path).touch()
                results.append(f'{C.D}created: {a}{C.NC}')
            except Exception as e:
                results.append(f'{C.R}[ERR] {a}: {e}{C.NC}')
        return ('\n'.join(results), 0)

    def _cmd_mkdir(self, args):
        if not args:
            return (f'{C.R}[ERR] Usage: mkdir [dir]{C.NC}', 1)
        results = []
        recursive = '-p' in args
        clean_args = [a for a in args if not a.startswith('-')]
        for a in clean_args:
            path = self._resolve_path(a)
            try:
                os.makedirs(path, exist_ok=True)
                results.append(f'{C.D}created: {a}{C.NC}')
            except Exception as e:
                results.append(f'{C.R}[ERR] {a}: {e}{C.NC}')
        return ('\n'.join(results), 0)

    def _cmd_rmdir(self, args):
        if not args:
            return (f'{C.R}[ERR] Usage: rmdir [dir]{C.NC}', 1)
        results = []
        for a in args:
            path = self._resolve_path(a)
            try:
                os.rmdir(path)
                results.append(f'{C.D}removed: {a}{C.NC}')
            except Exception as e:
                results.append(f'{C.R}[ERR] {a}: {e}{C.NC}')
        return ('\n'.join(results), 0)

    def _cmd_rm(self, args):
        if not args:
            return (f'{C.R}[ERR] Usage: rm [file|dir]{C.NC}', 1)
        results = []
        recursive = '-r' in args or '-rf' in args or '-R' in args
        clean_args = [a for a in args if not a.startswith('-')]
        for a in clean_args:
            path = self._resolve_path(a)
            try:
                if os.path.isdir(path):
                    if recursive:
                        shutil.rmtree(path)
                        results.append(f'{C.D}removed: {a}/{C.NC}')
                    else:
                        os.rmdir(path)
                        results.append(f'{C.D}removed: {a}/{C.NC}')
                elif os.path.isfile(path):
                    os.remove(path)
                    results.append(f'{C.D}removed: {a}{C.NC}')
                else:
                    results.append(f'{C.R}[ERR] No such file: {a}{C.NC}')
            except Exception as e:
                results.append(f'{C.R}[ERR] {a}: {e}{C.NC}')
        return ('\n'.join(results), 0)

    def _cmd_cp(self, args):
        if len(args) < 2:
            return (f'{C.R}[ERR] Usage: cp [src] [dst]{C.NC}', 1)
        src = self._resolve_path(args[0])
        dst = self._resolve_path(args[1])
        try:
            if os.path.isdir(src):
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
            return (f'{C.D}copied: {args[0]} -> {args[1]}{C.NC}', 0)
        except Exception as e:
            return (f'{C.R}[ERR] {e}{C.NC}', 1)

    def _cmd_mv(self, args):
        if len(args) < 2:
            return (f'{C.R}[ERR] Usage: mv [src] [dst]{C.NC}', 1)
        src = self._resolve_path(args[0])
        dst = self._resolve_path(args[1])
        try:
            shutil.move(str(src), str(dst))
            return (f'{C.D}moved: {args[0]} -> {args[1]}{C.NC}', 0)
        except Exception as e:
            return (f'{C.R}[ERR] {e}{C.NC}', 1)

    def _cmd_df(self, args):
        try:
            result = subprocess.run(['df', '-h'], capture_output=True, text=True, timeout=5)
            return (result.stdout, result.returncode)
        except:
            return (f'{C.R}[ERR] df not available{C.NC}', 1)

    def _cmd_du(self, args):
        target = args[0] if args else '.'
        path = self._resolve_path(target)
        try:
            total = 0
            for dirpath, dirnames, filenames in os.walk(path):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    try:
                        total += os.path.getsize(fp)
                    except:
                        pass
            if total > 1024*1024*1024:
                size = f'{total/(1024*1024*1024):.1f}G'
            elif total > 1024*1024:
                size = f'{total/(1024*1024):.1f}M'
            elif total > 1024:
                size = f'{total/1024:.1f}K'
            else:
                size = f'{total}B'
            return (f'{size}\t{target}', 0)
        except Exception as e:
            return (f'{C.R}[ERR] {e}{C.NC}', 1)

    def _cmd_free(self, args):
        try:
            result = subprocess.run(['free', '-h'], capture_output=True, text=True, timeout=5)
            return (result.stdout, result.returncode)
        except:
            return (f'{C.R}[ERR] free not available{C.NC}', 1)

    def _cmd_uptime(self, args):
        return (self._get_uptime(), 0)

    def _cmd_ps(self, args):
        try:
            result = subprocess.run(['ps', 'aux'] if 'aux' in args else ['ps'], capture_output=True, text=True, timeout=5)
            return (result.stdout, result.returncode)
        except:
            return (f'{C.R}[ERR] ps not available{C.NC}', 1)

    def _cmd_kill(self, args):
        if not args:
            return (f'{C.R}[ERR] Usage: kill [pid]{C.NC}', 1)
        try:
            pid = int(args[0])
            os.kill(pid, signal.SIGTERM)
            return (f'{C.D}killed pid {pid}{C.NC}', 0)
        except ProcessLookupError:
            return (f'{C.R}[ERR] No such process: {args[0]}{C.NC}', 1)
        except PermissionError:
            return (f'{C.R}[ERR] Permission denied: {args[0]}{C.NC}', 1)
        except ValueError:
            return (f'{C.R}[ERR] Invalid PID: {args[0]}{C.NC}', 1)

    def _cmd_chmod(self, args):
        if len(args) < 2:
            return (f'{C.R}[ERR] Usage: chmod [mode] [file]{C.NC}', 1)
        mode = args[0]
        path = self._resolve_path(args[1])
        try:
            os.chmod(path, int(mode, 8))
            return (f'{C.D}chmod {mode} {args[1]}{C.NC}', 0)
        except Exception as e:
            return (f'{C.R}[ERR] {e}{C.NC}', 1)

    def _cmd_wget(self, args):
        if not args:
            return (f'{C.R}[ERR] Usage: wget [url]{C.NC}', 1)
        return self._exec_system(['wget'] + args)

    def _cmd_curl(self, args):
        if not args:
            return (f'{C.R}[ERR] Usage: curl [url]{C.NC}', 1)
        return self._exec_system(['curl'] + args)

    def _cmd_python(self, args):
        if not args:
            return (f'{C.G}Python {platform.python_version()}{C.NC}\n{C.D}Usage: python3 [file.py] or python3 -c "code"{C.NC}', 0)

        if args[0] == '-c' and len(args) > 1:
            code = ' '.join(args[1:])
            try:
                result = subprocess.run(
                    [sys.executable, '-c', code],
                    capture_output=True, text=True, timeout=10,
                    cwd=str(self.cwd),
                )
                output = result.stdout + result.stderr
                return (output if output.strip() else '', result.returncode)
            except Exception as e:
                return (f'{C.R}[ERR] {e}{C.NC}', 1)
        else:
            path = self._resolve_path(args[0])
            if not os.path.isfile(path):
                return (f'{C.R}[ERR] No such file: {args[0]}{C.NC}', 1)
            try:
                result = subprocess.run(
                    [sys.executable, path] + args[1:],
                    capture_output=True, text=True, timeout=30,
                    cwd=str(self.cwd),
                )
                output = result.stdout + result.stderr
                return (output if output.strip() else '', result.returncode)
            except Exception as e:
                return (f'{C.R}[ERR] {e}{C.NC}', 1)

    def _cmd_pip(self, args):
        if not args:
            return (f'{C.R}[ERR] Usage: pip [install|list|remove] [package]{C.NC}', 1)
        return self._exec_system([sys.executable, '-m', 'pip'] + args)

    def _cmd_git(self, args):
        if not args:
            return (f'{C.R}[ERR] Usage: git [clone|pull|push|status|log|...]{C.NC}', 1)
        return self._exec_system(['git'] + args)

    def _cmd_npm(self, args):
        if not args:
            return (f'{C.R}[ERR] Usage: npm [install|run|...]{C.NC}', 1)
        return self._exec_system(['npm'] + args)

    def _cmd_node(self, args):
        if not args:
            return (f'{C.R}[ERR] Usage: node [file.js]{C.NC}', 1)
        return self._exec_system(['node'] + args)

    # ─── Myan Package Manager ───────────────────────────────────────────────
    def _cmd_myan(self, args):
        """📦 Myan Package Manager — real package management"""
        if not args or args[0] in ('help', '-h', '--help'):
            return (f"""{C.BD}📦 Myan Package Manager v2.0.0{C.NC}
{C.D}Myanmar's Advanced Package Manager{C.NC}

{C.Y}Commands:{C.NC}
  myan list              {C.D}List installed packages{C.NC}
  myan available         {C.D}List available .myan packages{C.NC}
  myan install [file]    {C.D}Install .myan package from file{C.NC}
  myan remove [name]     {C.D}Remove installed package{C.NC}
  myan search [query]    {C.D}Search installed packages{C.NC}
  myan info [name]       {C.D}Show package details{C.NC}
  myan update            {C.D}Update package index{C.NC}
  myan upgrade           {C.D}Upgrade all packages{C.NC}
  myan build [opts]      {C.D}Build .myan package

{C.Y}Examples:{C.NC}
  myan install ./dist/myanmar-code-2.0.1.myan
  myan remove myanmar-code
  myan list
  myan search code

{C.D}Package format: .myan (ZIP + MANIFEST.json + CHECKSUM.sha256){C.NC}""", 0)

        action = args[0]

        try:
            sys.path.insert(0, str(BASE_DIR))
            from myan_pm import MyanPM
            pm = MyanPM()

            if action == 'list':
                # Capture pm.list() output
                from io import StringIO
                old_stdout = sys.stdout
                sys.stdout = StringIO()
                pm.list()
                output = sys.stdout.getvalue()
                sys.stdout = old_stdout
                return (output if output.strip() else f'{C.D}(no packages installed){C.NC}', 0)

            elif action == 'available':
                dist_dir = BASE_DIR / 'dist'
                if not dist_dir.exists():
                    return (f'{C.D}No packages available{C.NC}', 0)
                lines = [f'{C.BD}📦 Available Packages:{C.NC}']
                for f in sorted(dist_dir.iterdir()):
                    if f.suffix == '.myan':
                        size_kb = f.stat().st_size / 1024
                        installed = self._is_pkg_installed(f.stem)
                        status = f'{C.G}✓ installed{C.NC}' if installed else f'{C.D}○ available{C.NC}'
                        lines.append(f'  {C.W}{f.name:<40}{C.NC}  {size_kb:>6.1f}KB  {status}')
                return ('\n'.join(lines), 0)

            elif action == 'install':
                if len(args) < 2:
                    return (f'{C.R}[ERR] Usage: myan install [file.myan | name]{C.NC}', 1)
                pkg_arg = args[1]
                # Resolve path
                if not pkg_arg.startswith('/') and not pkg_arg.startswith('./'):
                    pkg_arg = self._resolve_path(pkg_arg)
                else:
                    pkg_arg = self._resolve_path(pkg_arg)

                if not os.path.isfile(pkg_arg):
                    # Try dist/ directory
                    dist_path = BASE_DIR / 'dist' / pkg_arg
                    if not dist_path.exists():
                        dist_path = BASE_DIR / 'dist' / f'{pkg_arg}.myan'
                    if dist_path.exists():
                        pkg_arg = str(dist_path)
                    else:
                        return (f'{C.R}[ERR] Package not found: {args[1]}{C.NC}\n{C.D}Use "myan available" to see packages{C.NC}', 1)

                from io import StringIO
                old_stdout = sys.stdout
                sys.stdout = StringIO()
                pm.install(pkg_arg)
                output = sys.stdout.getvalue()
                sys.stdout = old_stdout
                return (output if output.strip() else f'{C.G}[OK] Package installed{C.NC}', 0)

            elif action == 'remove':
                if len(args) < 2:
                    return (f'{C.R}[ERR] Usage: myan remove [name]{C.NC}', 1)
                from io import StringIO
                old_stdout = sys.stdout
                sys.stdout = StringIO()
                pm.remove(args[1])
                output = sys.stdout.getvalue()
                sys.stdout = old_stdout
                return (output if output.strip() else f'{C.G}[OK] Package removed{C.NC}', 0)

            elif action == 'search':
                if len(args) < 2:
                    return (f'{C.R}[ERR] Usage: myan search [query]{C.NC}', 1)
                from io import StringIO
                old_stdout = sys.stdout
                sys.stdout = StringIO()
                pm.search(args[1])
                output = sys.stdout.getvalue()
                sys.stdout = old_stdout
                return (output if output.strip() else f'{C.D}(no results){C.NC}', 0)

            elif action == 'info':
                if len(args) < 2:
                    return (f'{C.R}[ERR] Usage: myan info [name]{C.NC}', 1)
                from io import StringIO
                old_stdout = sys.stdout
                sys.stdout = StringIO()
                pm.info(args[1])
                output = sys.stdout.getvalue()
                sys.stdout = old_stdout
                return (output if output.strip() else f'{C.D}Package not found{C.NC}', 0)

            elif action == 'update':
                return (f'{C.G}[OK] Package index updated{C.NC}\n{C.D}Use "myan available" to see packages{C.NC}', 0)

            elif action == 'upgrade':
                # Upgrade = reinstall all from dist/
                dist_dir = BASE_DIR / 'dist'
                if not dist_dir.exists():
                    return (f'{C.D}No packages to upgrade{C.NC}', 0)
                lines = [f'{C.Y}⬆ Upgrading all packages...{C.NC}']
                for f in sorted(dist_dir.iterdir()):
                    if f.suffix == '.myan':
                        lines.append(f'  {C.D}Installing {f.name}...{C.NC}')
                        try:
                            from io import StringIO
                            old_stdout = sys.stdout
                            sys.stdout = StringIO()
                            pm.install(str(f))
                            sys.stdout = old_stdout
                            lines.append(f'  {C.G}✓ {f.name}{C.NC}')
                        except Exception as e:
                            lines.append(f'  {C.R}✗ {f.name}: {e}{C.NC}')
                lines.append(f'\n{C.G}[OK] Upgrade complete{C.NC}')
                return ('\n'.join(lines), 0)

            elif action == 'build':
                # Delegate to myan_pm build
                from io import StringIO
                old_stdout = sys.stdout
                sys.stdout = StringIO()
                pm.build(args[1:])
                output = sys.stdout.getvalue()
                sys.stdout = old_stdout
                return (output if output.strip() else f'{C.G}[OK] Build complete{C.NC}', 0)

            else:
                return (f'{C.R}[ERR] Unknown myan command: {action}{C.NC}\n{C.D}Type "myan help" for commands{C.NC}', 1)

        except ImportError as e:
            return (f'{C.R}[ERR] MyanPM not available: {e}{C.NC}\n{C.D}Make sure myan_pm.py is in the Myanos directory{C.NC}', 1)
        except Exception as e:
            return (f'{C.R}[ERR] myan {action}: {e}{C.NC}', 1)

    def _is_pkg_installed(self, name):
        db_path = BASE_DIR / '.myan_db.json'
        if not db_path.exists():
            return False
        try:
            with open(db_path) as f:
                db = json.load(f)
            installed = db.get('packages', {})
            pkg_name = name.rsplit('-', 1)[0] if '-' in name else name
            return pkg_name in installed or name in installed
        except:
            return False

    # ─── Myanmar Code ───────────────────────────────────────────────────────
    def _cmd_mmc(self, args):
        """🇲🇲 Myanmar Code execution"""
        if not args or args[0] in ('help', '-h'):
            return (f"""{C.G}🇲🇲 Myanmar Code v2.0.1{C.NC}
{C.D}မြန်မာဘာသာစကားဖြင့် ရေးသားနိုင်သော ပရိုဂရမ်းမင်းဘာသာစကား{C.NC}
Author: Aung MoeOo (MWD) | 127 keywords

{C.Y}Usage:{C.NC}
  mmc [myanmar_code]
  mmc "ပုံနှိပ် \\\"မင်္ဂလာပါ\\\""

{C.Y}Install:{C.NC}
  pip install myanmar-code

{C.Y}Keywords (127):{C.NC}
  ပုံနှိပ်(print) တိုက်(if) တိုက်ရွေး(else) ပျက်(break)
  ဆက်လုပ်(continue) ပြန်ပေး(return) လုပ်ငန်း(function) ဖြတ်(class)
  ကြာအောင်(while) ပြည့်အောင်(end) ကိန်း(int) လော့ဂရစ်သမ်(float)
  စာ(string) မှန်(true) မှာ(false) ကိုယ်(self)...""", 0)

        code = ' '.join(args)
        try:
            import myanmar_code
            result = myanmar_code.execute(code)
            if result:
                return (str(result), 0)
            return ('', 0)
        except ImportError:
            return (f'{C.Y}[INFO] myanmar-code not installed{C.NC}\n{C.D}Install: pip install myanmar-code{C.NC}', 1)
        except Exception as e:
            return (f'{C.R}[ERR] mmc: {e}{C.NC}', 1)

    # ─── History ───────────────────────────────────────────────────────────
    def _load_history(self):
        global HISTORY
        if HISTORY_FILE.exists():
            try:
                with open(HISTORY_FILE) as f:
                    HISTORY = [line.strip() for line in f if line.strip()]
            except:
                HISTORY = []

    def _add_history(self, cmd):
        global HISTORY
        HISTORY.append(cmd)
        if len(HISTORY) > MAX_HISTORY:
            HISTORY = HISTORY[-MAX_HISTORY:]
        try:
            with open(HISTORY_FILE, 'w') as f:
                f.write('\n'.join(HISTORY) + '\n')
        except:
            pass


# ─── Standalone Interactive Mode ────────────────────────────────────────────
def run_interactive():
    """Run MMR Shell interactively in terminal"""
    import readline

    print(BANNER)
    shell = MMRShell()

    while True:
        try:
            # Build prompt with current dir
            cwd_str = str(shell.cwd)
            if cwd_str.startswith(str(HOME)):
                cwd_str = '~' + cwd_str[len(str(HOME)):]
            prompt = f"{C.G}meonnmi{C.NC}@{C.B}myanos{C.NC}:{C.C}{cwd_str}{C.NC}$ "

            cmd = input(prompt).strip()
            if not cmd:
                continue

            output, status = shell.execute(cmd)

            if output == 'exit':
                print(f'\n{C.D}Goodbye!{C.NC}')
                break
            elif output == '__CLEAR__':
                print('\033[2J\033[H', end='')
            elif output:
                # Remove ANSI for non-terminal? No, keep colors
                print(output)

        except KeyboardInterrupt:
            print(f'\n{C.D}^C{C.NC}')
        except EOFError:
            print(f'\n{C.D}Goodbye!{C.NC}')
            break
        except Exception as e:
            print(f'{C.R}[ERR] {e}{C.NC}')


if __name__ == '__main__':
    if len(sys.argv) > 1:
        # Execute single command
        shell = MMRShell()
        cmd = ' '.join(sys.argv[1:])
        output, status = shell.execute(cmd)
        if output:
            print(output, end='')
        sys.exit(status)
    else:
        run_interactive()
