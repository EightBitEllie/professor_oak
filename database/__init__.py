import asyncio
import json
import random
from typing import Dict, Optional

import yaml
import peewee
import peeweedbevolve
from discord.ext.commands import Bot, Cog
from playhouse import db_url

from shared import configuration

POOL = db_url.connect(configuration.get('db'))

HASHES: Dict[str, str] = {}
FLAVORS: Dict[str, list] = {}
PHASHES: Dict[str, str] = {}

class BaseModel(peewee.Model):
    class Meta:
        database = POOL


class HashMixin:
    pokemon = None
    def load_name(self) -> None:
        raise NotImplementedError()

    @property
    def name(self) -> Optional[str]:
        self.load_name()
        if self.pokemon is None:
            return None
        return self.pokemon.name

    @property
    def flavor(self) -> Optional[str]:
        if self.pokemon is None:
            return None
        return self.pokemon.flavor


class Player(BaseModel):
    discord_id = peewee.BigIntegerField(null=False, unique=True)
    name = peewee.CharField(null=True, max_length=32, default=None)
    active = peewee.BooleanField(default=False)


class Pokemon(BaseModel):
    name = peewee.CharField(null=True, unique=True, max_length=32)

    def random_flavor(self) -> None:
        if not FLAVORS:
            with open('flavors.json', mode='r') as f:
                FLAVORS.update(json.load(f))
        pokemon_flavors = FLAVORS.get(self.name.lower())
        if pokemon_flavors is None:
            return None
        return random.choice(pokemon_flavors)

    @property
    def flavor(self) -> Optional[str]:
        return self.random_flavor()


class Image(BaseModel, HashMixin):
    md5 = peewee.CharField(null=False, unique=True, max_length=32)
    pokemon = peewee.ForeignKeyField(Pokemon, backref='images', null=True)

    def load_name(self) -> None:
        if self.pokemon and self.pokemon.name:
            return
        if not HASHES:
            with open('imagehashes.json', mode='r') as f:
                HASHES.update({value["hash"]: value["name"]
                               for value in json.load(f)})
        name = HASHES.get(self.md5)
        if name is not None:
            if self.pokemon is None:
                pkmn, _ = Pokemon.get_or_create(name=name)
                self.pokemon = pkmn
            self.pokemon.name = name
            self.save()


class PHash(BaseModel, HashMixin):
    phash = peewee.CharField(null=False, unique=True, max_length=32)
    pokemon = peewee.ForeignKeyField(Pokemon, backref='images', null=True)

    def load_name(self) -> None:
        if self.pokemon and self.pokemon.name:
            return
        if not PHASHES:
            with open('phashes.yaml', mode='r') as f:
                PHASHES.update({value[1]: value[0] for value in yaml.safe_load(f).items()})
        name = PHASHES.get(self.phash)
        if name is not None:
            if self.pokemon is None:
                pkmn, _ = Pokemon.get_or_create(name=name)
                self.pokemon = pkmn
            self.pokemon.name = name
            self.save()

class PokedexEntry(BaseModel):
    pokemon = peewee.ForeignKeyField(Pokemon)
    person = peewee.ForeignKeyField(Player)
    caught = peewee.BooleanField(null=True)

    def checkmark(self) -> str:
        if self.caught is None:
            return '❓'
        elif self.caught:
            return '✅'
        return '❌'


class Database(Cog):
    def __init__(self, bot: Bot):
        self.bot = bot
        self.pool = POOL
        if bot is not None:
            bot.pool = self.pool

    def get_player(self, discord_id: int) -> Player:
        user, _ = Player.get_or_create(discord_id=discord_id)
        return user

    def check_player(self, discord_id: int) -> Optional[Player]:
        try:
            user = Player.get(discord_id=discord_id)
            return user
        except Player.DoesNotExist:
            return None

    def get_pokemon_image_by_hash(self, hashstr: str) -> Image:
        pkmn, _ = Image.get_or_create(md5=hashstr)
        return pkmn

    def get_pokemon_image_by_phash(self, hashstr: str) -> PHash:
        pkmn, _ = PHash.get_or_create(phash=hashstr)
        return pkmn


    def get_pokemon_by_name(self, name: str) -> Pokemon:
        pkmn, _ = Pokemon.get_or_create(name=name)
        return pkmn

    def get_pokedex_entry(self, player_id: int, pkmn_name: str) -> PokedexEntry:
        player = self.get_player(player_id)
        pkmn = self.get_pokemon_by_name(pkmn_name)
        entry, _ = PokedexEntry.get_or_create(pokemon=pkmn, person=player)
        return entry

    def __enter__(self) -> 'Database':
        if self.pool.is_closed():
            self.pool.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.pool.close()


POOL.evolve(interactive=False, ignore_tables=['BaseModel'])


def setup(bot: Bot) -> None:
    bot.add_cog(Database(bot))
