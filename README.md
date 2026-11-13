# framewise

## Running it

The repo has two parts:

- `backend/`: the Python 3.13 FastAPI backend and the `framewise` command, managed with [`uv`](https://docs.astral.sh/uv/). `uv` installs and pins its own Python 3.13, so the system Python is untouched.
- `frontend/`: the Angular 22 Review UI. Angular 22 needs Node.js 22.22.3+, 24.15+ or 26+.

Build the Review UI once, so the backend can serve it:

```sh
cd frontend
npm install
npx ng build
```

Then review a Session:

```sh
cd backend
uv run framewise review /path/to/session-folder
```

This scans the folder, stores its Frames in the Session store under `~/Library/Application Support/framewise/`, starts the server on `http://127.0.0.1:8765/` and opens the browser. Use `--port` to pick another port. `FRAMEWISE_DATA_DIR` overrides the Session store folder. If the Review UI has not been built, `framewise review` warns you to run `npx ng build` in `frontend/`.

## Tests

```sh
cd backend && uv run pytest && uv run ruff check .
cd frontend && npx ng test --watch=false
```
