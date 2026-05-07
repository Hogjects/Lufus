# Lufus

<div align="center">

<a href="https://github.com/Hog185/Lufus/blob/main/LICENSE">![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)</a>
<a href="https://discord.gg/QrbHJuYvzB">![Discord](https://img.shields.io/discord/1477694881127469202?style=flat\&logo=https%3A%2F%2Fcdn.discordapp.com%2Ficons%2F1477694881127469202%2F1b2c4e8defc9220de11098108fa1ed81.webp%3Fsize%3D256\&logoColor=rgb\&label=Join%20Server\&link=https%3A%2F%2Fdiscord.gg%2FTMnXwezsyV)</a>
<a href="#beta-release-disclaimer">![Status: Beta](https://img.shields.io/badge/status-beta-orange)</a>

<img width="64" height="64" alt="lufus" src="https://github.com/user-attachments/assets/0442203e-af37-4f51-97d4-433cfe946e25" />
</div>

## Beta Release Disclaimer

**Lufus** is currently in **Beta**! 

Lufus is a physical drive imaging and formatting utility written in Python, inspired by **Rufus** on Windows, with the goal of delivering a greater experience for Linux users.
While core functionality has been implemented, the project is still under active development. Users should expect bugs, incomplete features, and ongoing structural changes.

<p align="center">
    <img width="706" height="902" alt="2 (1)" src="https://github.com/user-attachments/assets/fd62ba76-9d14-4c3d-8167-defc8a2762e9" />
</p>

## Aim

Lufus aims to:

* Simplify bootable media creation for  Linux users (new and old alike)
* Provide a clean, minimal, and accessible interface for users
* Become an all in one hub for everything-flashing on Linux and provide features not offered yet by its counterparts
* Allow users freedom and control over their Windows installs (in works)
* and much more

## Running Lufus

Currently, running the project can be done by installing briefcase in a venv with
```
python3 -m venv venv
source venv/bin/activate
pip install briefcase
```
Clone the project, and run the following in the root directory of the project:
```briefcase dev -r```

## Documentation
Lufus uses [MkDocs](https://www.mkdocs.org/) for its documentation.
To build the docs locally, simply `pip install mkdocs` in the venv and run `mkdocs build`,
or `mkdocs serve` to run a dev server.

[Read the documentation here (WIP)](https://splayer.4plt.ch/lufus/)
## Contributing

Feedback, testing, translations, and other contributions are appreciated. Please join our Discord server to get quick support on contributing and debugging.
This is an open-source project maintained by volunteers and hobbyists. Response times for issues and pull requests may vary.
