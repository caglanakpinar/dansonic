from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_TRAILING_VARIANT = re.compile(r"^(.+?)(\d+)$")
_IMAGE_SUFFIXES = {".jpeg", ".jpg", ".png"}


@dataclass
class MoveAsset:
    """A named move: its reference sketches (for humans to read), the sound
    it triggers, and where its recorded pose template lives once one has
    been captured with `template_recorder`.
    """

    name: str
    sound_path: Path
    reference_images: list[Path]
    template_path: Path

    @property
    def has_template(self) -> bool:
        return self.template_path.exists()


def _base_name(stem: str) -> str:
    """Strips a trailing numeric variant suffix, so "ab2" and "ab" group
    under the same move "ab" (a move's sketches are its start/end
    keyframes, e.g. ab.jpeg + ab2.jpeg).
    """
    match = _TRAILING_VARIANT.match(stem)
    return match.group(1) if match else stem


class MoveLibrary:
    """Pairs move sketches in `moves_dir` with same-named sound files in
    `sounds_dir` by filename stem, so those two folders stay the single
    source of truth for what moves exist and what they sound like.
    """

    def __init__(
        self,
        moves_dir: str | Path = "dansonic_move",
        sounds_dir: str | Path = "dansonic_sounds",
        templates_dir: str | Path | None = None,
    ):
        self.moves_dir = Path(moves_dir)
        self.sounds_dir = Path(sounds_dir)
        self.templates_dir = Path(templates_dir) if templates_dir else self.moves_dir / "templates"
        self.moves = self._discover()

    def _discover(self) -> dict[str, MoveAsset]:
        # The sound files are the authoritative move list: a move exists
        # only if it has something to play. An image whose own stem has a
        # dedicated sound (e.g. ab2.jpeg + ab2.mp3) is its own move; only
        # images with no dedicated sound (e.g. been2.jpeg, with no
        # been2.mp3) fall back to grouping under their stripped base name
        # as an extra keyframe of that move (e.g. been2.jpeg -> "been").
        move_names = {
            sound_path.stem
            for sound_path in (sorted(self.sounds_dir.iterdir()) if self.sounds_dir.exists() else [])
            if sound_path.suffix.lower() == ".mp3"
        }

        images_by_move: dict[str, list[Path]] = {}
        for image_path in sorted(self.moves_dir.iterdir()) if self.moves_dir.exists() else []:
            if image_path.suffix.lower() not in _IMAGE_SUFFIXES:
                continue
            stem = image_path.stem
            if stem in move_names:
                move_name = stem
            else:
                move_name = _base_name(stem)
            images_by_move.setdefault(move_name, []).append(image_path)

        moves: dict[str, MoveAsset] = {}
        for move_name in move_names:
            moves[move_name] = MoveAsset(
                name=move_name,
                sound_path=self.sounds_dir / f"{move_name}.mp3",
                reference_images=sorted(images_by_move.get(move_name, [])),
                template_path=self.templates_dir / f"{move_name}.json",
            )
        return moves

    def missing_templates(self) -> list[str]:
        return sorted(name for name, asset in self.moves.items() if not asset.has_template)
