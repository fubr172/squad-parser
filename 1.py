import re
import logging
import os
import time
import keyboard

# Настройка логирования
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


def parse_log_block(lines):
    """Обработка блока строк логов."""
    results = []

    for line in lines:
        # Применяем паттерны в порядке вероятности
        for action, pattern in patterns.items():
            if pattern.match(line):  # Используем match вместо search
                match = pattern.match(line)
                data = match.groupdict()
                result = format_event(action, data)

                if result:
                    results.append(result)
                break  # Остановимся на первом найденном совпадении

    return results


def format_event(action, data):
    """Форматирует события в удобочитаемый текст."""
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
        return (
            f"{timestamp} Игрок {player_name} с EOS ID {eos_id} и Steam ID {steam_id} покинул транспорт {vehicle_name} "
            f"({asset_name}) на сиденье {seat_number}.")


class LogProcessor:
    def __init__(self, file_path):
        self.file_path = file_path

    def read_existing_lines(self):
        """Чтение всех существующих строк из файла при запуске."""
        if not os.path.isfile(self.file_path):
            print(f"Ошибка: Файл не найден по пути: {self.file_path}")
            return []

        try:
            with open(self.file_path, 'r', encoding='utf-8') as file:
                lines = file.readlines()
                return lines

        except (IOError, OSError) as e:
            print(f"Ошибка при чтении файла: {str(e)}")
            return []

    def tail_file(self):
        """Чтение новых строк в реальном времени."""
        with open(self.file_path, 'r', encoding='utf-8') as file:
            file.seek(0, os.SEEK_END)
            while True:
                line = file.readline()
                if line:
                    yield line
                else:
                    time.sleep(0.1)

    def run(self):
        existing_lines = self.read_existing_lines()
        if not existing_lines:
            print("Ошибка: Файл пуст или не удалось прочитать.")
            return

        results = parse_log_block(existing_lines)
        for result in results:
            print(result)

        for new_line in self.tail_file():
            results = parse_log_block([new_line])
            for result in results:
                print(result)

if __name__ == "__main__":
    log_file_path = "C:\\Users\\Fubar\\Downloads\\SquadGam.log"  # путь к файлу

    log_processor = LogProcessor(log_file_path)

    print("Программа запущена. Для выхода нажмите Enter.")
    while True:
        log_processor.run()

        if keyboard.is_pressed('enter'):
            print("Завершаю работу...")
            break

        time.sleep(0.1)
