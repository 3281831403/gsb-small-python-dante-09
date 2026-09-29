import copy
import os
import sys

ITEMS_TO_WIN = 6


def show_map():
    """Open Map.png in a desktop session; stay quiet-safe when headless."""
    if not sys.stdin.isatty():
        return
    try:
        from PIL import Image
        Image.open('Map.png').show()
    except Exception:
        print('Map: Map.png')


def prompt():
    print("\t\tWelcome to my game\n\n\
You must collect all six items before fighting the boss.\n\n\
Moves:\t'go {direction}' (travel north, south, east, or west)\n\
\t'get {item}' (add nearby item to inventory)\n")
    input("Press any key to continue...")


def clear():
    if sys.stdout.isatty():
        os.system('cls' if os.name == 'nt' else 'clear')


# Static map data, mirrors Map.png exactly. Treated as read-only: the game
# always operates on deep copies so this table can never be mutated.
ROOMS = {
    'Liminal Space': {'North': 'Mirror Maze', 'South': 'Bat Cavern', 'East': 'Bazaar'},
    'Mirror Maze': {'South': 'Liminal Space', 'Item': 'Crystal'},
    'Bat Cavern': {'North': 'Liminal Space', 'East': 'Volcano', 'Item': 'Staff'},
    'Bazaar': {'West': 'Liminal Space', 'North': 'Meat Locker', 'East': 'Dojo',
               'Item': 'Altoids'},
    'Meat Locker': {'South': 'Bazaar', 'East': 'Quicksand Pit', 'Item': 'Fig Newton'},
    'Quicksand Pit': {'West': 'Meat Locker', 'Item': 'Robe'},
    'Volcano': {'West': 'Bat Cavern', 'Item': 'Elderberry Syrup'},
    'Dojo': {'West': 'Bazaar', 'Boss': 'Shadow Self'},
}

DIRECTIONS = ('North', 'South', 'East', 'West')
VOWELS = ('a', 'e', 'i', 'o', 'u')
START_ROOM = 'Liminal Space'
START_HEALTH = 3
VALID_STATUSES = ('playing', 'won', 'lost', 'quit')


def fresh_world():
    """Deep copy of the map table; every game owns its own world."""
    return copy.deepcopy(ROOMS)


class GameState:
    """Game state. Commands either build a fully valid new state or return
    this object untouched (full rollback on failure)."""

    def __init__(self, current_room=START_ROOM, inventory=(), health=START_HEALTH,
                 status='playing', world=None):
        if current_room not in ROOMS:
            raise ValueError(f'Unknown room: {current_room!r}')
        if status not in VALID_STATUSES:
            raise ValueError(f'Unknown status: {status!r}')
        self.current_room = current_room
        self.inventory = tuple(sorted(inventory))
        self.health = health
        self.status = status
        self.world = world if world is not None else fresh_world()

    def snapshot(self):
        return copy.deepcopy({
            'current_room': self.current_room,
            'inventory': self.inventory,
            'health': self.health,
            'status': self.status,
            'world': self.world,
        })

    def clone(self):
        return GameState(self.current_room, self.inventory, self.health,
                         self.status, copy.deepcopy(self.world))


def new_game():
    return GameState()


def parse_command(user_input):
    words = user_input.strip().split()
    if not words:
        return '', ()
    return words[0].title(), tuple(word.title() for word in words[1:])


def _move(state, direction):
    exits = state.world[state.current_room]
    if direction not in exits:
        return state, "You can't go that way."

    next_state = state.clone()
    next_room = exits[direction]
    next_state.current_room = next_room

    boss = next_state.world[next_room].get('Boss')
    if boss is not None:
        if len(next_state.inventory) < ITEMS_TO_WIN:
            next_state.health = 0
            next_state.status = 'lost'
            return next_state, f'You lost a fight with {boss}.'
        next_state.status = 'won'
        return next_state, f'You beat {boss}!'

    return next_state, f'You travel {direction}'


def _get_item(state, targets):
    if not targets:
        return state, "Can't find that"
    name = ' '.join(targets)
    room_item = state.world[state.current_room].get('Item')
    if room_item is None:
        return state, f"Can't find {name}"
    if name in state.inventory:
        return state, f'You already have the {name}'
    if name != room_item:
        return state, f"Can't find {name}"

    next_state = state.clone()
    del next_state.world[state.current_room]['Item']  # write-back: room loses it
    next_state.inventory = tuple(sorted(state.inventory + (name,)))
    return next_state, f'{name} retrieved!'


def apply_command(state, user_input):
    """Apply one command transactionally.

    Returns (next_state, message). A failing command returns the *same*
    state object with nothing mutated, so failures can never leak into
    later commands.
    """
    if state.status != 'playing':
        return state, "The game is over. Type 'exit' to quit."

    action, targets = parse_command(user_input)

    if action == 'Go':
        if len(targets) != 1 or targets[0] not in DIRECTIONS:
            return state, "You can't go that way."
        return _move(state, targets[0])

    if action == 'Get':
        return _get_item(state, targets)

    if action == 'Exit':
        next_state = state.clone()
        next_state.status = 'quit'
        return next_state, 'Goodbye!'

    return state, 'Invalid command'


def describe_item(item):
    if item.endswith('s'):
        return f'You see {item}'
    article = 'an' if item[0].lower() in VOWELS else 'a'
    return f'You see {article} {item}'


def render(state, msg):
    print(f'You are in the {state.current_room}')
    print(f'Inventory : {list(state.inventory)}')
    print(f'Health    : {state.health}')
    print('-' * 27)
    print(msg)
    item = state.world[state.current_room].get('Item')
    if item is not None and item not in state.inventory:
        print(describe_item(item))


def run(commands):
    """Drive a game from an iterable of command strings (deterministic)."""
    state = new_game()
    msg = ''
    for command in commands:
        state, msg = apply_command(state, command)
        if state.status in ('won', 'lost', 'quit'):
            break
    return state, msg


def main():
    show_map()
    clear()
    prompt()

    state = new_game()
    msg = ''
    while True:
        clear()
        render(state, msg)
        if state.status in ('won', 'lost'):
            break
        try:
            user_input = input('Enter your move:\n')
        except EOFError:
            break
        state, msg = apply_command(state, user_input)
        if state.status == 'quit':
            print(msg)
            break


if __name__ == '__main__':
    main()
