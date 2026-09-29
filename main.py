import copy
import os
import sys

# Show map (optional; the game runs headless too)
def show_map():
    if not sys.stdin.isatty():
        print("Map: Map.png")
        return
    try:
        from PIL import Image
        Image.open('Map.png').show()
    except Exception:
        print("Map: Map.png")


# Display starting menu
def prompt():
    print("\t\tWelcome to my game\n\n\
You must collect all six items before fighting the boss.\n\n\
Moves:\t'go {direction}' (travel north, south, east, or west)\n\
\t'get {item}' (add nearby item to inventory)\n")

    input("Press any key to continue...")


# Clear screen (only in a real terminal)
def clear():
    if sys.stdout.isatty():
        os.system('cls' if os.name == 'nt' else 'clear')


# Map: this table mirrors Map.png exactly and is treated as read-only data.
ROOMS = {
    'Liminal Space': {'North': 'Mirror Maze', 'South': 'Bat Cavern', 'East': 'Bazaar'},
    'Mirror Maze': {'South': 'Liminal Space', 'Item': 'Crystal'},
    'Bat Cavern': {'North': 'Liminal Space', 'East': 'Volcano', 'Item': 'Staff'},
    'Bazaar': {'West': 'Liminal Space', 'North': 'Meat Locker', 'East': 'Dojo', 'Item': 'Altoids'},
    'Meat Locker': {'South': 'Bazaar', 'East': 'Quicksand Pit', 'Item': 'Fig Newton'},
    'Quicksand Pit': {'West': 'Meat Locker', 'Item': 'Robe'},
    'Volcano': {'West': 'Bat Cavern', 'Item': 'Elderberry Syrup'},
    'Dojo': {'West': 'Bazaar', 'Boss': 'Shadow Self'},
}

DIRECTIONS = ('North', 'South', 'East', 'West')
VOWELS = ('a', 'e', 'i', 'o', 'u')
START_ROOM = 'Liminal Space'
START_HEALTH = 3


def fresh_world():
    """A deep copy of the map so the shared ROOMS table is never mutated."""
    return copy.deepcopy(ROOMS)


class GameState:
    """Immutable-ish state; apply_command builds a new instance or returns
    the original unchanged when a command fails (full rollback)."""

    def __init__(self, current_room=START_ROOM, inventory=(), health=START_HEALTH,
                 status='playing', world=None):
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


def new_game():
    return GameState()


def parse_command(user_input):
    words = user_input.strip().split()
    if not words:
        return '', ()
    return words[0].title(), tuple(word.title() for word in words[1:])


def apply_command(state, user_input):
    """Apply one command transactionally.

    Returns (next_state, message). On failure the exact same state object is
    returned and nothing is mutated, so a failed move can never pollute the
    next move.
    """
    if state.status != 'playing':
        return state, "The game is over. Type 'exit' to quit."

    action, targets = parse_command(user_input)

    if action == 'Exit':
        return GameState(state.current_room, state.inventory, state.health,
                         'quit', copy.deepcopy(state.world)), "Goodbye!"

    if action == 'Go':
        if len(targets) != 1 or targets[0] not in DIRECTIONS:
            return state, "You can't go that way."
        direction = targets[0]
        room = state.world[state.current_room]
        if direction not in room:
            return state, "You can't go that way."
        next_state = GameState(state.current_room, state.inventory, state.health,
                               state.status, copy.deepcopy(state.world))
        next_room = room[direction]
        next_state.current_room = next_room

        if 'Boss' in next_state.world[next_room]:
            if len(next_state.inventory) < 6:
                next_state.health = 0
                next_state.status = 'lost'
                return next_state, f"You lost a fight with {next_state.world[next_room]['Boss']}."
            next_state.status = 'won'
            return next_state, f"You beat {next_state.world[next_room]['Boss']}!"

        return next_state, f"You travel {direction}"

    if action == 'Get':
        if not targets:
            return state, "Can't find that"
        item = " ".join(targets)
        room_item = state.world[state.current_room].get('Item')
        if room_item is None or item != room_item:
            return state, f"Can't find {item}"
        if item in state.inventory:
            return state, f"You already have the {item}"
        next_world = copy.deepcopy(state.world)
        del next_world[state.current_room]['Item']
        next_state = GameState(state.current_room,
                               state.inventory + (item,),
                               state.health, state.status, next_world)
        return next_state, f"{item} retrieved!"

    if action == '':
        return state, "Invalid command"

    return state, "Invalid command"


def describe_item(item):
    if item.endswith('s'):
        return f"You see {item}"
    article = 'an' if item[0].lower() in VOWELS else 'a'
    return f"You see {article} {item}"


def render(state, msg):
    print(f"You are in the {state.current_room}")
    print(f"Inventory : {list(state.inventory)}")
    print(f"Health    : {state.health}")
    print('-' * 27)
    print(msg)
    room = state.world[state.current_room]
    if 'Item' in room:
        print(describe_item(room['Item']))


def main():
    show_map()
    clear()
    prompt()

    state = new_game()
    msg = ""

    while True:
        clear()
        render(state, msg)

        if state.status == 'won' or state.status == 'lost':
            break

        try:
            user_input = input("Enter your move:\n")
        except EOFError:
            break

        state, msg = apply_command(state, user_input)
        if state.status == 'quit':
            print(msg)
            break


if __name__ == '__main__':
    main()
