"""Run the cup simulation. No serial, SDK, camera, cloud or calibration is opened."""
import argparse
import json
from uuid import uuid4

from .coordinator import Coordinator
from .perception.simulated_table import SimulatedTable, SCENARIOS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--web', action='store_true', help='Serve the existing /camera bench on loopback')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--scripted', action='store_true', help='Explicitly simulate both user and spotter for smoke testing')
    args = parser.parse_args()
    if args.web:
        import os
        import uvicorn
        from .api import create_app
        from .cup_bridge import CupDemo
        token, spotter = os.getenv('OPTIS_TOKEN'), os.getenv('OPTIS_SPOTTER_TOKEN')
        if not token or not spotter or token == spotter:
            parser.error('Set distinct OPTIS_TOKEN and OPTIS_SPOTTER_TOKEN values')
        uvicorn.run(create_app(token=token, spotter_token=spotter, database=os.getenv('OPTIS_DB'),
                              cup_demo=CupDemo()), host='127.0.0.1', port=args.port)
        return
    coordinator = Coordinator(trace=lambda event: print(json.dumps(event), flush=True))
    table = SimulatedTable(coordinator)
    table.thread.start()
    try:
        if args.scripted:
            # Two synthetic frames, no wall-clock wait required for admission.
            with table.lock:
                table.tick()
                table.tick()
            coordinator.enable()
            pending = coordinator.submit('retrieve', 'cup', request_id=uuid4().hex)
            coordinator.approve(pending['task_id'])
            coordinator.worker.join(timeout=10)
            if coordinator.status()['state'] != 'complete':
                raise SystemExit('Simulated workflow failed')
            return
        print('SIMULATION ONLY. user Put the cup in the tray | user stop | spotter enable | '
              'spotter approve TASK_ID | spotter reset | scenario '+ '/'.join(SCENARIOS)+' | quit')
        for line in iter(input, ''):
            text = line.strip()
            if text == 'quit':
                break
            if text == 'spotter enable':
                coordinator.enable()
            elif text == 'spotter reset':
                coordinator.reset()
            elif text.startswith('spotter approve '):
                coordinator.approve(text.removeprefix('spotter approve '))
            elif text.startswith('scenario '):
                try:
                    table.set_scenario(text.removeprefix('scenario '))
                except ValueError as error:
                    print(error)
            elif text.lower() == 'user put the cup in the tray':
                coordinator.submit('retrieve', 'cup', request_id=uuid4().hex)
            elif text.lower() == 'user stop':
                coordinator.stop()
            else:
                print('Unknown command; approval is available only with the spotter prefix.')
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        coordinator.close()
        table.close()


if __name__ == '__main__':
    main()
