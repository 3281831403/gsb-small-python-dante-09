import copy
import subprocess
import sys
import unittest

import main


def snapshot(state):
    """Deep-copy snapshot: later mutations must never alter an earlier shot."""
    return copy.deepcopy({
        'room': state.current_room,
        'inventory': state.inventory,
        'health': state.health,
        'status': state.status,
        'world': state.world,
    })


def make(room=main.START_ROOM, inventory=(), health=main.START_HEALTH,
         status='playing', items_picked=()):
    world = main.fresh_world()
    for picked_room in items_picked:
        world[picked_room].pop('Item', None)
    return main.GameState(room, tuple(inventory), health, status, world)


# Each row: (name, command, state-builder kwargs, expected delta,
# message substring). expected_delta of None means the exact same state
# object must come back and its deep snapshot must equal the before-shot.
# fmt: off
TABLE = [
    ('go north',                       'go north',        {}, {'room': 'Mirror Maze'}, 'You travel North'),
    ('go south',                       'go south',        {}, {'room': 'Bat Cavern'}, 'You travel South'),
    ('go east',                        'go east',         {}, {'room': 'Bazaar'}, 'You travel East'),
    ('go back west',                   'go west',         {'room': 'Bazaar'}, {'room': 'Liminal Space'}, 'You travel West'),
    ('go upper-case',                  'GO EAST',         {}, {'room': 'Bazaar'}, 'You travel East'),
    ('go mixed-case',                  'Go NoRtH',        {}, {'room': 'Mirror Maze'}, 'You travel North'),
    ('go west blocked',                'go west',         {}, None, "can't go that way"),
    ('go nonsense direction',          'go sideways',     {}, None, "can't go that way"),
    ('go missing target',              'go',              {}, None, "can't go that way"),
    ('go extra target',                'go north now',    {}, None, "can't go that way"),
    ('unknown verb',                   'dance',           {}, None, 'Invalid command'),
    ('whitespace only',                '   ',             {}, None, 'Invalid command'),
    ('unknown verb mixed case',        'FrOBNICATE',      {}, None, 'Invalid command'),
    ('unknown verb with args',         'open sesame',     {}, None, 'Invalid command'),
    ('exit quits',                     'exit',            {}, {'status': 'quit'}, 'Goodbye'),
    ('get crystal',                    'get crystal',     {'room': 'Mirror Maze'},
        {'room': 'Mirror Maze', 'inventory': ('Crystal',), 'picked': ('Mirror Maze',)}, 'Crystal retrieved'),
    ('get fig newton two words',       'get fig newton',  {'room': 'Meat Locker'},
        {'room': 'Meat Locker', 'inventory': ('Fig Newton',), 'picked': ('Meat Locker',)}, 'Fig Newton retrieved'),
    ('get elderberry syrup two words', 'get elderberry syrup', {'room': 'Volcano'},
        {'room': 'Volcano', 'inventory': ('Elderberry Syrup',), 'picked': ('Volcano',)}, 'Elderberry Syrup retrieved'),
    ('get staff',                      'get staff',       {'room': 'Bat Cavern'},
        {'room': 'Bat Cavern', 'inventory': ('Staff',), 'picked': ('Bat Cavern',)}, 'Staff retrieved'),
    ('get altoids plural',             'get altoids',     {'room': 'Bazaar'},
        {'room': 'Bazaar', 'inventory': ('Altoids',), 'picked': ('Bazaar',)}, 'Altoids retrieved'),
    ('get robe',                       'get robe',        {'room': 'Quicksand Pit'},
        {'room': 'Quicksand Pit', 'inventory': ('Robe',), 'picked': ('Quicksand Pit',)}, 'Robe retrieved'),
    ('get wrong item rolls back',      'get sword',       {'room': 'Mirror Maze'}, None, "Can't find Sword"),
    ('get item not in this room',      'get crystal',     {'room': 'Bazaar'}, None, "Can't find Crystal"),
    ('get in itemless room',           'get crystal',     {'room': 'Quicksand Pit'}, None, "Can't find Crystal"),
    ('get with no target',             'get',             {'room': 'Mirror Maze'}, None, "Can't find"),
    ('get already owned rolls back',   'get crystal',
        {'room': 'Mirror Maze', 'inventory': ('Crystal',)}, None, 'already have'),
    ('get other-room item rolls back', 'get staff',       {'room': 'Mirror Maze'}, None, "Can't find Staff"),
    ('boss loss with five items',      'go east',
        {'room': 'Bazaar', 'inventory': ('Altoids', 'Crystal', 'Elderberry Syrup',
                                         'Fig Newton', 'Robe'),
         'items_picked': ('Mirror Maze', 'Bazaar', 'Meat Locker',
                          'Quicksand Pit', 'Volcano')},
        {'room': 'Dojo', 'health': 0, 'status': 'lost'}, 'lost a fight with Shadow Self'),
    ('boss win with six items',        'go east',
        {'room': 'Bazaar',
         'inventory': ('Altoids', 'Crystal', 'Elderberry Syrup',
                       'Fig Newton', 'Robe', 'Staff'),
         'items_picked': ('Mirror Maze', 'Bat Cavern', 'Bazaar', 'Meat Locker',
                          'Quicksand Pit', 'Volcano')},
        {'room': 'Dojo', 'health': 3, 'status': 'won'}, 'You beat Shadow Self'),
    ('commands after loss ignored',    'go north',
        {'room': 'Dojo', 'health': 0, 'status': 'lost'}, None, 'game is over'),
    ('commands after win ignored',     'get crystal',
        {'room': 'Dojo', 'health': 3, 'status': 'won'}, None, 'game is over'),
]
# fmt: on

WIN_SCRIPT = [
    'go north', 'get crystal',
    'go south', 'go south', 'get staff',
    'go east', 'get elderberry syrup',
    'go west', 'go north', 'go east', 'get altoids',
    'go north', 'get fig newton',
    'go east', 'get robe',
    'go west', 'go south', 'go east',
]

# Commands that are invalid from *every* room regardless of traversal.
INTERLEAVE_JUNK = ('go northwest', 'go sideways', 'get sword',
                   'dance', '', 'get')


class TableDrivenTests(unittest.TestCase):
    def _check_row(self, name, command, kwargs, expected_delta, msg_part):
        state = make(**kwargs)
        before = snapshot(state)

        result_state, message = main.apply_command(state, command)

        self.assertIn(msg_part, message, f'{name}: message mismatch')
        if expected_delta is None:
            self.assertIs(result_state, state,
                          f'{name}: failed command must return the same object')
            self.assertEqual(snapshot(result_state), before,
                             f'{name}: failed command must fully roll back')
        else:
            picked = expected_delta.get('picked', ())
            expected = copy.deepcopy(before)
            for room_name in picked:
                expected['world'][room_name].pop('Item', None)
            for key, value in expected_delta.items():
                if key == 'picked':
                    continue
                expected[key] = value
            self.assertEqual(snapshot(result_state), expected,
                             f'{name}: committed state mismatch')
            self.assertIsNot(result_state, state,
                             f'{name}: committed command must return a new state')

    def test_table_driven_rows(self):
        self.assertGreaterEqual(len(TABLE), 12)
        for row in TABLE:
            with self.subTest(case=row[0]):
                self._check_row(*row)

    def test_snapshots_are_deep_independent_copies(self):
        state = make(room='Meat Locker')
        shot1 = snapshot(state)
        state, _ = main.apply_command(state, 'get fig newton')
        shot2 = snapshot(state)
        # Mutating one snapshot must not touch the state or other snapshots.
        shot1['world']['Meat Locker']['Item'] = 'Hacked'
        shot1['room'] = 'Dojo'
        shot2['inventory'] = ('X',)
        shot2['world']['Meat Locker']['North'] = 'Nowhere'
        self.assertEqual(state.world['Meat Locker'].get('Item'), None)
        self.assertEqual(state.current_room, 'Meat Locker')
        self.assertEqual(state.inventory, ('Fig Newton',))
        self.assertNotIn('North', state.world['Meat Locker'])
        self.assertEqual(snapshot(state)['inventory'], ('Fig Newton',))

    def test_global_rooms_table_never_mutated(self):
        baseline = copy.deepcopy(main.ROOMS)
        state = main.new_game()
        for command in ('go north', 'get crystal', 'go south', 'go sideways',
                        'get', 'dance', 'go south', 'get staff'):
            main.apply_command(state, command)
        self.assertEqual(main.ROOMS, baseline)
        # The live world may lose items; the global table must keep them.
        self.assertEqual(main.ROOMS['Mirror Maze']['Item'], 'Crystal')

    def test_pickup_write_back_survives_following_moves(self):
        state = make(room='Meat Locker')
        state, _ = main.apply_command(state, 'get fig newton')
        state, _ = main.apply_command(state, 'go west')  # blocked -> rollback
        state, _ = main.apply_command(state, 'go south')
        state, _ = main.apply_command(state, 'go north')
        self.assertNotIn('Item', state.world['Meat Locker'])
        self.assertIn('Fig Newton', state.inventory)
        # Item cannot be collected a second time: after write-back the room
        # no longer offers it, so the re-get fails and rolls back.
        again, msg = main.apply_command(state, 'get fig newton')
        self.assertIs(again, state)
        self.assertTrue('already have' in msg or "Can't find" in msg)

    def test_failures_do_not_pollute_later_commands(self):
        def run(script):
            state = main.new_game()
            shots = [snapshot(state)]
            for command in script:
                state, _ = main.apply_command(state, command)
                shots.append(snapshot(state))
            return shots

        clean = run(WIN_SCRIPT)
        for junk in INTERLEAVE_JUNK:
            polluted = []
            for command in WIN_SCRIPT:
                polluted.extend([junk, command])
            result = run(polluted)
            # After each failing junk command the snapshot is unchanged...
            self.assertEqual(result[1::2][: len(clean) - 1], clean[:-1],
                             f'junk {junk!r} mutated state')
            # ...and the post-real-command snapshots match the clean run.
            self.assertEqual(result[2::2], clean[1:],
                             f'junk {junk!r} polluted the next command')

    def test_result_independent_of_traversal_order(self):
        def run():
            state = main.new_game()
            shots = []
            for command in WIN_SCRIPT:
                state, _ = main.apply_command(state, command)
                shots.append(snapshot(state))
            return state, shots

        end_state, shots = run()
        self.assertEqual(end_state.status, 'won')
        self.assertEqual(len(end_state.inventory), 6)
        self.assertEqual(end_state.health, 3)

        # Reverse every room's key order; outcomes must be identical.
        saved = {name: list(room.items()) for name, room in main.ROOMS.items()}
        try:
            for room in main.ROOMS.values():
                entries = list(room.items())
                room.clear()
                for key, value in reversed(entries):
                    room[key] = value
            rev_state, rev_shots = run()
        finally:
            for name, room in main.ROOMS.items():
                entries = dict(saved[name])
                room.clear()
                room.update(entries)

        self.assertEqual(rev_shots, shots)
        self.assertEqual(rev_state.status, 'won')
        self.assertEqual(tuple(rev_state.inventory), tuple(end_state.inventory))

    def test_deterministic_inventory_order(self):
        state = make(room='Volcano', inventory=('Zebra Item', 'Apple Item'))
        state, _ = main.apply_command(state, 'get elderberry syrup')
        self.assertEqual(state.inventory,
                         ('Apple Item', 'Elderberry Syrup', 'Zebra Item'))

    def test_determinism_across_repeated_runs(self):
        endings = set()
        for _ in range(5):
            state, _ = main.run(WIN_SCRIPT)
            endings.add((state.status, state.health, state.inventory,
                         state.current_room))
        self.assertEqual(len(endings), 1)

    def test_loss_path_sets_health_and_status(self):
        state = main.new_game()
        state, _ = main.apply_command(state, 'go east')
        state, msg = main.apply_command(state, 'go east')
        self.assertEqual(state.status, 'lost')
        self.assertEqual(state.health, 0)
        self.assertEqual(state.current_room, 'Dojo')
        self.assertIn('Shadow Self', msg)

    def test_full_win_path(self):
        state, msg = main.run(WIN_SCRIPT)
        self.assertEqual(state.status, 'won')
        self.assertEqual(state.health, 3)
        self.assertEqual(len(state.inventory), 6)
        self.assertIn('Shadow Self', msg)
        for room_name, room in state.world.items():
            if room_name != 'Dojo':
                self.assertNotIn('Item', room)

    def test_health_unchanged_by_normal_play(self):
        state = main.new_game()
        for command in WIN_SCRIPT[:-1]:
            state, _ = main.apply_command(state, command)
            self.assertEqual(state.health, 3)


class HeadlessRunTests(unittest.TestCase):
    def test_runs_headless_via_stdin(self):
        proc = subprocess.run(
            [sys.executable, 'main.py'],
            input='\n' + '\n'.join(WIN_SCRIPT) + '\n',
            capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn('You beat Shadow Self', proc.stdout)

    def test_eof_only_does_not_crash(self):
        proc = subprocess.run([sys.executable, 'main.py'], input='\n',
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_loss_headless(self):
        proc = subprocess.run(
            [sys.executable, 'main.py'],
            input='\ngo east\ngo east\n',
            capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn('lost a fight with Shadow Self', proc.stdout)


if __name__ == '__main__':
    unittest.main()
