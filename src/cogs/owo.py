import logging
from asyncio import sleep as async_sleep
from random import choice as random_choice, randrange as random_range

from disnake import Message
from disnake.ext import commands

from owomatic.bot import Owomatic

logger = logging.getLogger(__package__)

OWO_VAULT = ["◕w◕", "σωσ", "◔w◔", "♥w♥", "𝓞𝔀𝓞", "𝙤𝙬𝙤", "uωu", "UωU", "OωO", "oωo", "OωO", "oωo"]
OWO_SENSE = ["owo", "uwu"]

NAVY_SEAL = [
    "What the fuck did you just fucking say about me, you little bitch?",
    "I'll have you know I graduated top of my class in the Navy Seals, and I've been involved in numerous secret raids on Al-Quaeda, and I have over ***300*** confirmed kills.",
    "I am trained in gorilla warfare and I'm the top sniper in the entire US armed forces. *You are nothing to me but just another target.*",
    "I will wipe you the fuck out with precision the likes of which has never been seen before on this Earth, mark my **fucking** words.",
    "You think you can get away with saying that shit to me over the Internet? *Think again, fucker.*",
    "As we speak I am contacting my secret network of spies across the USA and your IP is being traced right now so you better prepare for the storm, *maggot.*",
    "The storm that wipes out the pathetic little thing you call your life. *You're fucking dead, kid.*",
    "I can be anywhere, anytime, and I can kill you in over seven hundred ways, and that's just with my bare hands.",
    "Not only am I extensively trained in unarmed combat, but I have access to the entire arsenal of the United States Marine Corps and I will use it to its full extent to wipe your miserable ass off the face of the continent, you little shit.",
    'If only you could have known what unholy retribution your little "clever" comment was about to bring down upon you, maybe you would have held your fucking tongue.',
    "But you couldn't, you didn't, and now you're paying the price, you goddamn idiot. I will shit fury all over you and you will drown in it.",
    "***You're fucking dead, kiddo.***",
]


def has_owo(message: Message) -> bool:
    msg_text = message.content.lower()
    owo = False
    if any(owo in msg_text for owo in OWO_SENSE):
        owo = True
    if any(owo in msg_text.replace(" ", "") for owo in OWO_SENSE):
        author = f"{message.author.name}#{message.author.discriminator}"
        logger.warn(f"non-standard owo detected! {author} thinks they're funny: '{message.content}'")
        owo = True
    return owo


class Owo(commands.Cog, name="template-slash"):
    def __init__(self, bot: Owomatic):
        self.bot = bot
        self.owo_pool = OWO_VAULT

    async def cog_load(self) -> None:
        logger.info("owo? what's this?")
        return await super().cog_load()

    async def cog_unload(self) -> None:
        return await super().cog_unload()

    def get_owo(self):
        # if we only have one option left, use that and reset the pool
        if len(self.owo_pool) == 1:
            owo = self.owo_pool[0]
            self.owo_pool = OWO_VAULT
        else:  # get a random owo from the pool and remove it from the pool
            owo = random_choice(self.owo_pool)
            self.owo_pool.remove(owo)
        return owo

    async def youre_dead_kiddo(self, message: Message):
        replied = False
        async with message.channel.typing():
            for line in NAVY_SEAL:
                if not replied:
                    await message.reply(line)
                    replied = True
                else:
                    await message.channel.send(line)
                await async_sleep(0.15)

    @commands.Cog.listener("on_message")
    async def on_message(self, message: Message):
        if (message.author.bot is True) or (message.author == self.bot.user):
            return

        if has_owo(message):
            logger.info("owo!")
            if random_range(0, 420) == 69 or (
                "fight me" in message.content.lower()
                and message.author.id == self.bot.owner_id
                and self.bot.user in message.mentions
            ):
                logger.info("oh now you've done it, champ")
                await self.youre_dead_kiddo(message)
            await message.channel.send(self.get_owo())


def setup(bot):
    bot.add_cog(Owo(bot))
