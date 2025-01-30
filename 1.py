import asyncio
import re
import logging
import subprocess
import time
from pathlib import Path
import aiofiles
import os
import sys
import keyboard

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.StreamHandler()])


# Регулярные выражения для поиска
patterns = {
    # Полученный урон
    'damage_received': re.compile(
        r'(?P<timestamp>\[\d{4}\.\d{2}\.\d{2}-\d{2}\.\d{2}\.\d{2}:\d{2}\])' 
        r'\[\s*\d+\]LogSquad:\s+PostLogin:\s+NewPlayer:\s+(?P<player_name>[^\s]+)\s+[^\(]+\s+\(IP:\s+(?P<ip>[\d\.]+)\s+\|\s+'
        r'Online IDs:\s+EOS:\s+(?P<eos_id>[0-9a-f]{32})\s+steam:\s+(?P<steam_id>\d+)\)'
    ),
    # Урон, приведший к убийству
    'killing_damage': re.compile(
        r'^(?P<timestamp>\[\d{4}\.\d{2}\.\d{2}-\d{2}\.\d{2}\.\d{2}:\d+\])\[\d+\]LogSquad:\s+'
        r'Player:\s+(?P<player>\S+)\s+ActualDamage=(?P<damage>[\d\.]+)\s+from\s+(?P<source>\S+)\s+'
        r'\(Online IDs:\s+EOS:\s+(?P<eos_id>[0-9a-f]{32})\s+steam:\s+(?P<steam_id>\d+)\s+\|\s+'
        r'Player Controller ID:\s+(?P<controller_id>[^\)]+)\)\s+caused by\s+(?P<causer>\S+)'
    ),
    # Ранение
    'wound': re.compile(
        r'^(?P<timestamp>\[\d{4}\.\d{2}\.\d{2}-\d{2}\.\d{2}\.\d{2}:\d+\])\[\d+\]'
        r'LogSquadTrace:\s+\[DedicatedServer\]ASQSoldier::Wound\(\):\s+Player:\s+(?P<player>\S+)\s+'
        r'KillingDamage=(?P<damage>[\d\.]+)\s+from\s+(?P<source>[^\s]+)\s+\('
        r'Online IDs:\s+(?P<online_id>[^\)]+)\)\s+EOS:\s+(?P<eos_id>[0-9a-f]{32})\s+'
        r'steam:\s+(?P<steam_id>\d+)\s+\|\s+Controller ID:\s+(?P<controller_id>[^\)]+)\)\s+caused by\s+(?P<causer>[^\s]+)'
    ),
    # Урон транспортному средству
    'vehicle_damage': re.compile(
        r'^(?P<timestamp>\[\d{4}\.\d{2}\.\d{2}-\d{2}\.\d{2}\.\d{2}:\d+\])\[\d+\]'
        r'LogSquadTrace:\s+\[DedicatedServer\]ASQVehicleSeat::'
        r'TraceAndMessageClient\(\):\s+(?P<weapon>\S+):\s+(?P<damage>[\d\.]+)\s+'
        r'damage taken by causer\s+(?P<causer>\S+)\s+instigator\s+\(Online Ids:\s+(?P<online_id>[^\)]+)\)\s+'
        r'EOS:\s+(?P<eos_id>[0-9a-f]{32})\s+steam:\s+(?P<steam_id>\d+)\s+health remaining\s+(?P<health>[\d\-\.]+)'
    ),
    # Смерть
    'death': re.compile(
        r'^(?P<timestamp>\[\d{4}\.\d{2}\.\d{2}-\d{2}\.\d{2}\.\d{2}:\d+\])]\[\d+\]'
        r'LogSquadTrace:\s+\[DedicatedServer\]ASQSoldier::Die\(\):\s+Player:\s+(?P<player>.*?)\s+'
        r'KillingDamage=(?P<damage>[\d\.]+)\s+from\s+(?P<source>[^\s]+)\s+\('
        r'Online IDs:\s+EOS:\s+(?P<eos_id>[0-9a-f]{32})\s+steam:\s+(?P<steam_id>\d+)\s+\|\s+'
        r'Controller ID:\s+(?P<controller_id>[^\)]+)\)\s+caused by\s+(?P<causer>[^\s]+)'
    ),
    # Урон от взрывчатки
    'explosive_damage': re.compile(
        r'^(?P<timestamp>\[\d{4}\.\d{2}\.\d{2}-\d{2}\.\d{2}\.\d{2}:\d+\])\[\s*\d+\]'
        r'LogSquadTrace:\s+\[DedicatedServer\]ASQProjectile:'
        r':ApplyExplosiveDamage\(\):\s+HitActor=(?P<hit_actor>\S+)\s+'
        r'DamageCauser=(?P<damage_causer>\S+)\s+DamageInstigator=(?P<damage_instigator>\S+)\s+'
        r'ExplosionLocation=V\(X=(?P<x>[-\d\.]+), Y=(?P<y>[-\d\.]+), Z=(?P<z>[-\d\.]+)\)'
    ),
    # Инициализация игрока
    'player_initialization': re.compile(
        r'(?P<timestamp>\[\d{4}\.\d{2}\.\d{2}-\d{2}\.\d{2}\.\d{2}:\d{2}\])\[\d+\]'
        r'LogGameMode:\s+Initialized player\s+(?P<player_name>\S+)\s+'
        r'with controller\s+(?P<controller_id>[^\s]+)\s+\(Steam ID:\s+(?P<steam_id>\d+)\)'
    ),
    # Убийство своей команды
    'team_kill': re.compile(
        r'(?P<killer>.*?) killed (?P<victim>.*?) \(team kill\)'
    ),
    # Подключение
    'connection': re.compile(
        r'^(?P<timestamp>\[\d{4}\.\d{2}\.\d{2}-\d{2}\.\d{2}\.\d{2}:\d+\])\[\d+\]LogSquad:\s+PostLogin:\s+'
        r'NewPlayer:\s+(?P<player_name>[^\s]+)\s+[^\(]+\s+\(IP:\s+(?P<ip>[\d\.]+)\s+\|\s+'
        r'Online IDs:\s+EOS:\s+(?P<eos_id>[0-9a-f]{32})\s+steam:\s+(?P<steam_id>\d+)\)'
    ),
    # Отключение
    'disconnection': re.compile(
        r'^(?P<timestamp>\[\d{4}\.\d{2}\.\d{2}-\d{2}\.\d{2}\.\d{2}:\d+\])\[\d+\]LogNet: UNetConnection::Close: '
        r'\[UNetConnection\] RemoteAddr:\s*(?P<remote_addr>[\d\.]+:\d+), '
        r'Name:\s*(?P<name>[^\s]+), '
        r'Driver:\s*(?P<driver>[^\s]+), '
        r'IsServer:\s*(?P<is_server>\w+), '
        r'PC:\s*(?P<pc>[^\s]+), '
        r'Owner:\s*(?P<owner>[^\s]+), '
        r'UniqueId:\s*(?P<unique_id>[^\s]+), '
        r'Channels:\s*(?P<channels>\d+), '
        r'Time:\s*(?P<time>[\d\.]+-\d{2}\.\d{2}\.\d{2})'
    ),
    # Результат матча
    'match_result': re.compile(
        r'^(?P<timestamp>\[\d{4}\.\d{2}\.\d{2}-\d{2}\.\d{2}\.\d{2}:\d+\])\[\d+\]'
        r'LogSquadGameEvents:\s+Display:\s+Team\s+(?P<team_number>\d+),\s+(?P<team_name>[^(]+)\s+\(\s*'
        r'(?P<full_team_name>[^)]+)\s*\)\s+(?P<result>wins|loses)\s+the\s+match\s+with\s+(?P<tickets>\d+)\s+'
        r'Tickets\s+on\s+layer\s+(?P<layer>[^\s]+)\s+\(level\s+(?P<level>[^\)]+)\)!'
    ),
    # Воскрешение игрока
    'player_revive': re.compile(
        r'^(?P<timestamp>\[\d{4}\.\d{2}\.\d{2}-\d{2}\.\d{2}\.\d{2}:\d+\])\[\d+\]LogSquad:\s+(?P<reviver>\S+)\s+\('
        r'Online IDs:\s+EOS:\s+(?P<reviver_eos>[0-9a-f]{32})\s+steam:\s+(?P<reviver_steam>\d+)\)\s+'
        r'has revived\s+(?P<revived>\S+)\s+\(Online IDs:\s+EOS:\s+(?P<revived_eos>[0-9a-f]{32})\s+'
        r'steam:\s+(?P<revived_steam>\d+)\)\.'
    ),
    'unpossess_vehicle': re.compile(
        r'^(?P<timestamp>\[\d{4}\.\d{2}\.\d{2}-\d{2}\.\d{2}\.\d{2}:\d+\])\[\d+\]LogSquadTrace:' 
        r'\s+\[DedicatedServer\]ASQPlayerController::OnUnPossess\(\):\s+PC=(?P<player_name>[^\s]+)' 
        r'\s+\(Online\s+IDs:\s+EOS:\s+(?P<eos_id>[0-9a-f]{32})\s+steam:\s+(?P<steam_id>\d+)\)\s+' 
        r'Exited\s+Vehicle\s+Pawn=(?P<vehicle_name>[^\s]+)\s+\(Asset\s+Name=(?P<asset_name>[^\s]+)\)\s+' 
        r'FullPath=(?P<full_path>[^\s]+)\s+Seat\s+Number=(?P<seat_number>\d+)\s*'
    ),
    'unpossess_vehicle': re.compile(
        r'^(?P<timestamp>\[\d{4}\.\d{2}\.\d{2}-\d{2}\.\d{2}\.\d{2}:\d+\])\[\d+\]LogSquadTrace:'
        r'\s+\[DedicatedServer\]ASQPlayerController::OnUnPossess\(\):\s+PC=(?P<player_name>[^\s]+)' 
        r'\s+\(Online\s+IDs:\s+EOS:\s+(?P<eos_id>[0-9a-f]{32})\s+steam:\s+(?P<steam_id>\d+)\)\s+' 
        r'Exited\s+Vehicle\s+Pawn=(?P<vehicle_name>[^\s]+)\s+\(Asset\s+Name=(?P<asset_name>[^\s]+)\)\s+' 
        r'FullPath=(?P<full_path>[^\s]+)\s+Seat\s+Number=(?P<seat_number>\d+)\s*'
    )
}

def format_event(action, data):
    """
    Formats game events into a human-readable string.

    This function takes an action type and corresponding data, and returns a formatted string
    that describes the event in detail.

    Args:
        action (str): The type of event being formatted (e.g., 'damage_received', 'death').
        data (dict): A dictionary containing relevant information for the event.

    Returns:
        str: A formatted string describing the event.

    Event Types:
        - 'damage_received': Describes when a player receives damage.
        - 'killing_damage': Describes when a player inflicts fatal damage on another player.
        - 'wound': Describes when a player is wounded.
        - 'vehicle_damage': Describes damage inflicted on a vehicle.
        - 'death': Describes when a player dies.
        - 'connection': Describes when a player connects to the server.
        - 'disconnection': Describes when a player disconnects from the server.
        - 'match_result': Describes the result of a match.
        - 'unpossess_vehicle': Describes when a player leaves a vehicle.

    If the action type is not recognized, it returns "Неизвестное событие." (Unknown event).
    """

    timestamp = data.get('timestamp')

    if action == 'damage_received':
        player_name = data.get('player_name', 'неизвестный игрок')
        source = data.get('source', 'неизвестный источник')
        damage = data.get('damage', '0')
        return f"{timestamp} Игрок {player_name} получил урон от {source} ({damage} единиц)."

    if action == 'killing_damage':
        player = data.get('player', 'неизвестный игрок')
        damage = data.get('damage', '0')
        source = data.get('source', 'неизвестное оружие')
        return f"{timestamp} Игрок {player} нанес смертельный урон ({damage} единиц) используя {source}."

    if action == 'wound':
        player = data.get('player', 'неизвестный игрок')
        damage = data.get('damage', '0')
        source = data.get('source', 'неизвестное оружие')
        causer = data.get('causer', 'неизвестная причина')
        return f"{timestamp} Игрок {player} был ранен {causer} с использованием {source} (урон: {damage})."

    if action == 'vehicle_damage':
        damage = data.get('damage', '0')
        causer = data.get('causer', 'неизвестный источник')
        weapon = data.get('weapon', 'неизвестное оружие')
        health = data.get('health', 'неизвестно')
        return (f"{timestamp} Транспорт получил {damage} урона от {causer} "
                f"с использованием {weapon}. Остаток здоровья: {health}.")

    if action == 'death':
        player = data.get('player', 'неизвестный игрок')
        causer = data.get('causer', 'неизвестный источник')
        source = data.get('source', 'неизвестное оружие')
        damage = data.get('damage', '0')
        return (f"{timestamp} Игрок {player} был убит {causer} "
                f"с использованием {source} (урон: {damage}).")

    if action == 'connection':
        player_name = data.get('player_name', 'неизвестный игрок')
        ip = data.get('ip', 'неизвестный IP')
        eos_id = data.get('eos_id', 'неизвестный EOS ID')
        steam_id = data.get('steam_id', 'неизвестный Steam ID')
        return (f"{timestamp} Игрок {player_name} подключился с IP: {ip} "
                f"(EOS ID: {eos_id}, Steam ID: {steam_id}).")

    if action == 'disconnection':
        name = data.get('name', 'неизвестный игрок')
        remote_addr = data.get('remote_addr', 'неизвестный адрес')
        time = data.get('time', 'неизвестное время')
        return f"{timestamp} Игрок {name} отключился. IP: {remote_addr}, Время: {time}."

    if action == 'match_result':
        team_number = data.get('team_number', 'неизвестная команда')
        team_name = data.get('team_name', 'неизвестное имя команды')
        result = data.get('result', 'неизвестный результат')
        tickets = data.get('tickets', '0')
        layer = data.get('layer', 'неизвестный слой')
        level = data.get('level', 'неизвестный уровень')
        return (f"{timestamp} Команда {team_number} ({team_name}) {result} матч "
                f"с {tickets} тикетами на слое {layer} (уровень: {level}).")

    if action == 'unpossess_vehicle':
        player_name = data.get('player_name', 'неизвестный игрок')
        eos_id = data.get('eos_id', 'неизвестный EOS ID')
        steam_id = data.get('steam_id', 'неизвестный Steam ID')
        vehicle_name = data.get('vehicle_name', 'неизвестный транспорт')
        asset_name = data.get('asset_name', 'неизвестный актив')
        seat_number = data.get('seat_number', 'неизвестное сиденье')
        
       # Note: This condition was duplicated in your original code; it should only appear once.
       return (
            f"{timestamp} Игрок {player_name} с EOS ID {eos_id} и Steam ID {steam_id} покинул транспорт {vehicle_name} "
            f"({asset_name}) на сиденье {seat_number}.")
    
    return "Неизвестное событие."

def parse_log_block(lines):
    """
    Processes a block of log lines and extracts formatted event information.

    Args:
        lines (list of str): A list of log lines to process.

    Returns:
        list of str: A list of formatted event strings extracted from the log lines.
    """
    results = []
    for line in lines:
        for action, pattern in patterns.items():
            match = pattern.match(line)
            if match:
                result = format_event(action, match.groupdict())
                if result:
                    results.append(result)
                break
    return results

class LogProcessor:
    """
    A class to handle reading and processing log files.

    Attributes:
        file_path (Path): The path to the log file.
    """

    def __init__(self, file_path):
        """
        Initializes the LogProcessor with the specified file path.

        Args:
            file_path (str): The path to the log file.
        """
        self.file_path = Path(file_path)

    def read_existing_lines(self):
        """
        Reads all existing lines from the log file at startup.

        Returns:
            list of str: A list of lines read from the file, or an empty list if an error occurs.
        """
        if not self.file_path.is_file():
            logging.error(f"Файл не найден: {self.file_path}")
            return []

        try:
            with self.file_path.open('r', encoding='utf-8', errors='ignore') as file:
                return file.readlines()
        except (IOError, OSError) as e:
            logging.error(f"Ошибка при чтении файла {self.file_path}: {e}")
            return []

    async def tail_file(self):
        """
        Reads new lines from the log file in real-time.

        Yields:
            str: New lines read from the file as they are added.
        """
        try:
            with self.file_path.open('r', encoding='utf-8', errors='ignore') as file:
                file.seek(0, os.SEEK_END)  # Move to the end of the file
                while True:
                    line = file.readline()
                    if line:
                        yield line.strip()  # Yield non-empty lines
                    else:
                        await asyncio.sleep(0.1)  # Wait briefly before checking again
        except Exception as e:
            logging.error(f"Ошибка при чтении {self.file_path}: {e}")

    async def run(self):
        """
        Processes logs in real-time by reading existing lines and then tailing the file for new entries.
        """
        existing_lines = self.read_existing_lines()
        if existing_lines:
            results = parse_log_block(existing_lines)
            for result in results:
                logging.info(result)

        async for new_line in self.tail_file():
            results = parse_log_block([new_line])
            for result in results:
                logging.info(result)

async def process_log_in_real_time(file_path):
    """
    Processes a specified log file in real-time.

    Args:
        file_path (str): The path to the log file to be processed.
    
    Raises:
        Exception: If an error occurs during processing.
    """
    try:
        processor = LogProcessor(file_path)
        await processor.run()
    except Exception as e:
        logging.error(f"Ошибка при обработке {file_path}: {e}")

async def process_multiple_files(files):
    """
    Processes multiple log files concurrently.

    Args:
        files (list of str): A list of paths to the log files to be processed.
    
    Raises:
        Exception: If an error occurs during processing.
    """
    tasks = [process_log_in_real_time(file) for file in files]
    await asyncio.gather(*tasks)

def process_file_in_new_console(file_path):
    """
    Launches processing of a specified log file in a new console window.

    Args:
        file_path (str): The path to the log file to be processed in a new console.
    
    Raises:
        Exception: If an error occurs while starting a new process.
    """
    script_path = Path(__file__).resolve()
    try:
        if os.name == "nt":
            subprocess.Popen(["python", script_path, "child", str(file_path)],
                             creationflags=subprocess.CREATE_NEW_CONSOLE)
        else:
            subprocess.Popen(["x-terminal-emulator", "-e", "python", script_path, "child", str(file_path)])
    except Exception as e:
        logging.error(f"Ошибка при запуске нового процесса: {e}")


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "child":
        file_to_process = sys.argv[2]
        asyncio.run(process_log_in_real_time(file_to_process))
        input("Нажмите Enter, чтобы закрыть окно...")
    else:
        files_to_process = [
            Path(r"").resolve(),
            Path(r"").resolve(),
            Path(r"").resolve(),
            Path(r"").resolve(),
        ]

        for file_path in files_to_process:
            process_file_in_new_console(file_path)
