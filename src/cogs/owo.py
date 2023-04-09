import json
import logging
from asyncio import sleep as async_sleep
from os import PathLike
from pathlib import Path
from random import choice, randrange, shuffle

from disnake import Message
from disnake.ext import commands

from owomatic.bot import Owomatic
from owomatic.helpers.deowo import deOwOify, realspace

COG_UID = "owo"

OWO_JSON = Path(__file__).parent.joinpath("data", "owo.json")

logger = logging.getLogger(__package__)

NAVY_SEAL = [
    "What the fuck did you just fucking say about me, you little bitch?",
    "I'll have you know I graduated top of my class in the Navy Seals, and I've been involved in numerous secret raids on Al-Quaeda, and I have over ***300*** confirmed kills.",
    "I am trained in gorilla warfare and I'm the top sniper in the entire US armed forces. *You are nothing to me but just another target.*",
    "I will wipe you the fuck out with precision the likes of which has never been seen before on this Earth, mark my **fucking** words.",
    "You think you can get away with saying that shit to me over the Internet? *Think again, fucker.*",
    "As we speak I am contacting my secret network of spies across the USA and your IP is being traced right now so you better prepare for the storm, *maggot*",
    "The storm that wipes out the pathetic little thing you call your life. *You're fucking dead, kid.*",
    "I can be anywhere, anytime, and I can kill you in over seven hundred ways, and that's just with my bare hands.",
    "Not only am I extensively trained in unarmed combat, but I have access to the entire arsenal of the United States Marine Corps and I will use it to its full extent to wipe your miserable ass off the face of the continent, you little shit.",
    'If only you could have known what unholy retribution your little "clever" comment was about to bring down upon you, maybe you would have held your fucking tongue.',
    "But you couldn't, you didn't, and now you're paying the price, you goddamn idiot. I will shit fury all over you and you will drown in it.",
    "***You're fucking dead, kiddo.***",
]

NAVY_UWU = [
    "what the fuck did you just fucking say about me, you wittwe bitch? >:3",
    "i'ww have you knyOwO i gwaduated top of my cwass in the Nyavy Seaws (・`ω´・), and i've been invowved in nyumewous secwet waids on aw-quaeda, and i have ovew ***300*** confiwmed kiwws.",
    "i am twained in gowiwwa wawfawe awnd i'm the top snipew in the entiwe us awmed fowces. \\*screams\\* *you awe nyothing t-to me but just anyothew tawget.*",
    "i wiww wipe uwu the fuck out with pwecision the wikes of which has nevew bewn seen befowe own thiws eawth, mawk my **fucking** wowds.",
    "you think uwu cawn get away with saying thawt shit tuwu me ovew the intewnet? *think again, fuckew.*",
    "as we speak i am contacting my secwet nyetwowk of spies acwoss the usa awnd youw ip is being twaced wight now so uwu bettew pwepawe fow the stowm, *maggOwOt*",
    "the stowm thawt wipes out the pathetic wittwe thing uwu caww youw wife. \\*screeches\\* *you'we fucking dead, kid.*",
    "i cawn be anywhewe, anytime, awnd i cawn kiww uwu in ovew seven hundwed ways, awnd thawt's juwst with my bawe hands (✿◠‿◠)",
    "not onwy am i extensivewy twained in unawmed combat, but i have access tuwu the entiwe awsenaw of the united states mawine cowr awnd i wiww use iwt 2 its fuww extent tuwu wipe youw misewabwe ass off the face of the continent, uwu wittwe shit.",
    'if onwy u couwd have known whawt unhowy wetwibution youw wittwe "cwevew" comment was abouwt tuwu bwing down upon uwu, maybe uwu wouwd have hewd youw fucking tongue.',
    "but uwu couwdn't, uwu didn't, awnd now uwu'we paying the pwice, uwu goddamn idiot. I wiww shit fuwy aww ovew u awnd uwu wiww dwown in iwt.",
    "✨·.·´¯\\`·.·✨  🎀 ***you'we fucking dead, kiddo.*** 🎀  ✨·.·\\`¯´·.·✨",
]


class OwoVault:
    def __init__(self):
        # load the owo data
        owodata: dict = json.loads(OWO_JSON.read_text())

        # make into some props
        owos = owodata.get("owos", [])
        uwus = owodata.get("uwus", [])
        self.fwinishews = owodata.get("finishers", owos)

        self._OwO: list[str] = owos + uwus
        self._vault = self.OwO

    @property
    def OwO(self):
        return self._OwO.copy()

    def refresh(self):
        if len(self._vault) == 0:
            self._vault = self.OwO
        shuffle(self._vault)

    def get(self, fwinish_him: bool = False):
        if fwinish_him:
            return choice(self.fwinishews)
        self.refresh()
        return self._vault.pop()

    def check(self, message: Message) -> bool:
        msg_text = realspace(message.content).lower()
        msg_unfucked = deOwOify(msg_text)
        author = f"{message.author.name}#{message.author.discriminator}"

        notices = False
        if any(owo in msg_text for owo in self._OwO):
            notices = True
        elif any(owo in msg_text.replace(" ", "") for owo in self._OwO if owo != "ono"):
            logger.debug(f"non-standard owo detected! {author} thinks they're funny: '{message.content}'")
            notices = True
        elif any(owo in msg_unfucked.replace(" ", "") for owo in self._OwO):
            logger.debug(f"LISTEN HERE YOU LITTLE SHIT. {author} thinks they're funny: '{message.content}'")
            notices = True
        return notices


class Owo(commands.Cog, name=COG_UID):
    def __init__(self, bot: Owomatic):
        self.bot = bot
        self.vault: OwoVault = None
        self.owo_allow: list[int] = self.bot.config["owo_channels"]["allowed"]
        self.owo_maybe: list[int] = self.bot.config["owo_channels"]["cooldown"]

    async def cog_load(self) -> None:
        logger.info("OwO what's this?")
        self.vault = OwoVault()
        logger.info(f"{self.vault.get()} is ready to go!!")
        return await super().cog_load()

    async def cog_unload(self) -> None:
        logger.info("oh nowo? bye bye!")
        return await super().cog_unload()

    async def youre_dead_kiddo(self, message: Message):
        replied = False
        async with message.channel.typing():
            for line in NAVY_UWU:
                if not replied:
                    await message.reply(line)
                    replied = True
                else:
                    await message.channel.send(line)
                await async_sleep(0.2)

    @commands.Cog.listener("on_message")
    async def on_message(self, message: Message):
        if (message.author.bot is True) or (message.author == self.bot.user):
            return

        if message.author.id in self.bot.config["owners"]:
            if "T_T" in message.content and message.channel.id in self.owo_allow:
                await message.channel.send("(+_+)")

        if message.content.startswith("```"):
            return

        if self.vault.check(message):
            logger.info("owo!")
            if message.channel.id in self.owo_allow:
                if randrange(0, 420) == 69 or (
                    "fight me" in message.content.lower()
                    and message.author.id == self.bot.owner_id
                    and self.bot.user in message.mentions
                ):
                    logger.info("oh now you've done it, champ")
                    await self.youre_dead_kiddo(message)
                await self.send_owo(message, fwinish_him=True)
            elif message.channel.id in self.owo_maybe and randrange(0, 9) == 7:
                await self.send_owo(message)
            else:
                logger.info("nowo :(")

    async def send_owo(self, message: Message, fwinish_him: bool = False):
        await message.channel.send(self.vault.get(fwinish_him))


def setup(bot):
    bot.add_cog(Owo(bot))
