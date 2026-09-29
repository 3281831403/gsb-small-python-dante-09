import copy
import unittest

import main


def snapshot(state):
    return copy.deepcopy({
        'room': state.current_room,
        'inventory': state.inventory,
        'health': state.health,
        'status': state.status,
        'world': state.world,
    })


def make(room=main.START_ROOM, inventory=(), health=main.START_HEALTH,
         status='playing', items_picked=()):
    """Build a state with items removed from the listed rooms (write-back)."""
    world = main.fresh_world()
    for picked_room in items_picked:
        world[picked_room].pop('Item', None)
    return main.GameState(room, tuple(inventory), health, status, world)


# fmt: off
TABLE = [
    # row, command, state-builder kwargs, expected delta (None => identical), expected message substring
    ('go north valid',                 'go north', {}, {'room': 'Mirror Maze'}, 'You travel North'),
    ('go south valid',                 'go south', {}, {'room': 'Bat Cavern'}, 'You travel South'),
    ('go case-insensitive direction',  'GO EAST',  {}, {'room': 'Bazaar'}, 'You travel East'),
    ('go west valid',                  'go west',  {'room': 'Bazaar'}, {'room': 'Liminal Space'}, 'You travel West'),
    ('go illegal direction rollback',  'go west',  {}, None, "You can't go that way"),
    ('go nonsense target rollback',    'go sideways', {}, None, "You can't go that way"),
    ('go missing target rollback',     'go',       {}, None, "You can't go that way"),
    ('invalid command rollback',       'dance',    {}, None, 'Invalid command'),
    ('empty command rollback',         '   ',      {}, None, 'Invalid command'),
    ('case-insensitive bad command',   'FrOBNICATE', {}, None, 'Invalid command'),
    ('quit ends game',                 'exit',     {}, {'status': 'quit'}, 'Goodbye'),
    ('get single word item',           'get crystal', {'room': 'Mirror Maze'},
        {'room': 'Mirror Maze', 'inventory': ('Crystal',), 'picked': ('Mirror Maze',)}, 'Crystal retrieved'),
    ('get multi word item fig newton', 'get fig newton', {'room': 'Meat Locker'},
        {'room': 'Meat Locker', 'inventory': ('Fig Newton',), 'picked': ('Meat Locker',)}, 'Fig Newton retrieved'),
    ('get elderberry syrup',           'get elderberry syrup', {'room': 'Volcano'},
        {'room': 'Volcano', 'inventory': ('Elderberry Syrup',), 'picked': ('Volcano',)}, 'Elderberry Syrup retrieved'),
    ('get wrong item rollback',        'get sword', {'room': 'Mirror Maze'}, None, "Can't find Sword"),
    ('get when no item in room',       'get crystal', {'room': 'Bazaar'}, None, "Can't find Crystal"),
    ('get with no target rollback',    'get',       {'room': 'Mirror Maze'}, None, "Can't find"),
    ('get duplicate item rollback',    'get crystal',
        {'room': 'Mirror Maze', 'inventory': ('Crystal',)},
        None, 'already have'),
    ('boss fight loss sets health',    'go east',
        {'room': 'Bazaar', 'inventory': ('Crystal',),
         'items_picked': ('Mirror Maze',)},
        {'room': 'Dojo', 'health': 0, 'status': 'lost'}, 'lost a fight'),
    ('boss fight win keeps health',    'go east',
        {'room': 'Bazaar',
         'inventory': ('Altoids', 'Crystal', 'Elderberry Syrup', 'Fig Newton', 'Robe', 'Staff'),
         'items_picked': ('Mirror Maze', 'Bat Cavern', 'Bazaar', 'Meat Locker',
                          'Quicksand Pit', 'Volcano')},
        {'room': 'Dojo', 'health': 3, 'status': 'won'}, 'beat Shadow Self'),
]
# fmt: on


class TableDrivenTests(unittest.TestCase):
    def _check_row(self, name, command, kwargs, expected_delta, msg_part):
        state = make(**kwargs)
        before = snapshot(state)

        returned_state, message = main.apply_command(state, command)

        if expected_delta is None:
            self.assertIs(returned_state, state, f'{name}: failed move must return same object')
            self.assertEqual(snapshot(returned_state), before,
                             f'{name}: failed move must fully roll back')
        else:
            expected = copy.deepcopy(before)
            picked_rooms = expected_delta.pop('picked', ())
            for picked_room in picked_rooms:
                expected['world'][picked_room].pop('Item', None)
            for key, value in expected_delta.items():
                expected[key] = value
            self.assertEqual(snapshot(returned_state), expected,
                             f'{name}: committed state mismatch')
        self.assertIn(msg_part, message)

    def test_table(self):
        for name, command, kwargs, expected_delta, msg_part in TABLE:
            with self.subTest(case=name):
                self._check_row(name, command, kwargs, expected_delta, msg_part)

    def test_at_least_twelve_cases(self):
        self.assertGreaterEqual(len(TABLE), 12)

    def test_rooms_table_never_mutated(self):
        rooms_snapshot = copy.deepcopy(main.ROOMS)
        for command in ('go north', 'get crystal', 'go sideways', 'get',
                        'go east', 'dance'):
            state = main.new_game()
            if command in ('get crystal', 'go east'):
                state = make(room='Mirror Maze' if command == 'get crystal' else 'Bazaar')
            main.apply_command(state, command)
        self.assertEqual(main.ROOMS, rooms_snapshot)

    def test_item_pickup_is_written_back_to_room(self):
        state = make(room='Meat Locker')
        before = snapshot(state)
        state, _ = main.apply_command(state, 'get fig newton')
        self.assertNotIn('Item', state.world['Meat Locker'])
        self.assertIn('Fig Newton', state.inventory)
        self.assertNotEqual(snapshot(state), before)
        # The change must survive a subsequent move.
        state, _ = main.apply_command(state, 'go south')
        self.assertNotIn('Item', state.world['Meat Locker'])
        self.assertIn('Fig Newton', state.inventory)

    def test_failed_move_does_not_pollute_next_move(self):
        base_script = [
            'go north', 'get crystal', 'go south', 'go south', 'get staff',
            'go east', 'get elderberry syrup', 'go west', 'go north',
            'go east', 'get altoids',
            'go north', 'get fig newton', 'go east', 'get robe',
            'go west', 'go south', 'go east',
        ]

        def run(script):
            state = main.new_game()
            shots = []
            for command in script:
                state, _ = main.apply_command(state, command)
                shots.append(snapshot(state))
            return shots

        clean = run(base_script)
        for junk in ('go nowhere', 'get missing thing', 'dance', '', 'get sword'):
            polluted_script = []
            for index, command in enumerate(base_script):
                polluted_script.append(junk)
                polluted_script.append(command)
            polluted = run(polluted_script)
            self.assertEqual(polluted[1::2], clean,
                             f'junk command {junk!r} polluted subsequent state')

    def test_result_independent_of_traversal_order(self):
        def run():
            state = main.new_game()
            sequence = [
                ('go north', 'Mirror Maze', 'get crystal'),
                ('go south', 'Liminal Space', None),
                ('go south', 'Bat Cavern', 'get staff'),
                ('go east', 'Volcano', 'get elderberry syrup'),
                ('go west', 'Bat Cavern', None),
                ('go north', 'Liminal Space', None),
                ('go east', 'Bazaar', 'get altoids'),
                ('go north', 'Meat Locker', 'get fig newton'),
                ('go east', 'Quicksand Pit', 'get robe'),
                ('go west', 'Meat Locker', None),
                ('go south', 'Bazaar', None),
                ('go east', 'Dojo', None),
            ]
            shots = []
            for go_cmd, _room, get_cmd in sequence:
                state, _ = main.apply_command(state, go_cmd)
                if get_cmd:
                    state, _ = main.apply_command(state, get_cmd)
                shots.append(snapshot(state))
            return state, shots

        end_state, _ = run()
        self.assertEqual(end_state.status, 'won')
        self.assertEqual(len(end_state.inventory), 6)

        # Reversed direction-key insertion order in the map must not matter.
        original_keys = {name: list(room.keys()) for name, room in main.ROOMS.items()}
        try:
            for room in main.ROOMS.values():
                entries = list(room.items())
                room.clear()
                for key, value in reversed(entries):
                    room[key] = value
            end_state_reversed, shots_reversed = run()
            _, shots = run()
            self.assertEqual(shots_reversed, shots)
            self.assertEqual(end_state_reversed.status, 'won')
        finally:
            for name, room in main.ROOMS.items():
                entries = list(room.items())
                room.clear()
                for key in original_keys[name]:
                    room[key] = dict(entries)[key]

    def test_inventory_is_deterministically_sorted(self):
        state = make(room='Volcano',
                     inventory=('Zebra Item', 'Apple Item'),
                     items_picked=())
        state, _ = main.apply_command(state, 'get elderberry syrup')
        self.assertEqual(state.inventory,
                         ('Apple Item', 'Elderberry Syrup', 'Zebra Item'))

    def test_deep_snapshot_is_independent_copy(self):
        state = main.new_game()
        shot = snapshot(state)
        shot['world']['Liminal Space']['North'] = 'Hacked'
        shot['inventory'] = ('X',)
        self.assertEqual(state.world['Liminal Space']['North'], 'Mirror Maze')
        self.assertEqual(state.inventory, ())

    def test_successful_get_removes_item_from_world_only(self):
        state = make(room='Bazaar')
        state, _ = main.apply_command(state, 'get altoids')
        self.assertNotIn('Item', state.world['Bazaar'])
        self.assertIn('Item', main.ROOMS['Bazaar'])

    def test_full_win_path(self):
        state = main.new_game()
        script = [
            'go north', 'get crystal',
            'go south', 'go south', 'get staff',
            'go east', 'get elderberry syrup',
            'go west', 'go north', 'go east', 'get altoids',
            'go north', 'get fig newton',
            'go east', 'get robe',
            'go west', 'go south', 'go east',
        ]
        for command in script:
            state, _ = main.apply_command(state, command)
        self.assertEqual(state.status, 'won')
        self.assertEqual(state.health, 3)
        self.assertEqual(len(state.inventory), 6)

    def test_loss_path(self):
        state = main.new_game()
        for command in ('go east', 'go east'):
            state, _ = main.apply_command(state, command)
        self.assertEqual(state.status, 'lost')
        self.assertEqual(state.health, 0)


if __name__ == '__main__':
    unittest.main()
