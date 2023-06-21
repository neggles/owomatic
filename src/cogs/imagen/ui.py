import asyncio
import logging
from typing import Dict, Optional, Union

from disnake import (
    ButtonStyle,
    Colour,
    Embed,
    File,
    Member,
    MessageInteraction,
    User,
    ui,
)
from disnake.ext import commands

from owomatic.bot import Owomatic

COG_UID = "imagen"
logger = logging.getLogger(__name__)


def response_to_fields(response: dict, model_name: str) -> dict:
    params: Dict = response["parameters"]
    info: Dict = response["info"]
    return {
        "Model": model_name,
        "Prompt": params["prompt"],
        "Negative": params["negative_prompt"],
        "Steps": params["steps"],
        "CFG Scale": params["cfg_scale"],
        "Denoise": params["denoising_strength"],
        "Seed": info["seed"],
        "Duration": response["gen_duration"],
    }


class ImagenEmbed(Embed):
    def __init__(
        self,
        image: Optional[File] = None,
        author: User | Member = ...,
        model_name: str = ...,
        api_response: dict = ...,
        **kwargs,
    ):
        super().__init__(
            colour=author.colour if isinstance(author, Member) else Colour(0xFFD01C),
            **kwargs,
        )
        logger.debug(f"Creating embed for user {author.display_name} ({author.id})")
        try:
            if api_response is not None:
                fields = response_to_fields(api_response, model_name)
                self.description = fields.pop("Prompt", ":shrug:")
                negative = fields.pop("Negative", "")
                if len(negative) > 0:
                    self.add_field(name="Negative", value=negative, inline=False)
                for key, val in fields.items():
                    self.add_field(name=key, value=val, inline=True)
            if image is not None:
                self.set_image(file=image)
            self.set_author(name=author.display_name, icon_url=author.display_avatar.url)
            self.set_footer(text="Powered by cursed python 😱🐍")
        except Exception as e:
            logger.error(e)
            raise e


class ImagenView(ui.View):
    def __init__(
        self,
        bot: Owomatic,
        author: Union[User, Member],
        model_name: str,
        request: dict,
    ):
        super().__init__(timeout=None)
        self.bot: Owomatic = bot
        self.cog = bot.get_cog(COG_UID)
        self.author = author
        self.model_name = model_name
        self.request = request

    @ui.button(label="Retry", style=ButtonStyle.green)
    async def retry_button(self, button: ui.Button, ctx: MessageInteraction):
        await ctx.response.defer()
        try:
            # Switch into disabled states to prevent double-clicking and race conditions
            self.retry_button.disabled = True
            self.retry_button.label = "Retrying..."
            self.retry_button.style = ButtonStyle.gray
            await ctx.edit_original_response(view=self)

            # Generate new embed
            logger.info(f"Retrying {COG_UID} generation for {ctx.author.display_name} ({ctx.author.id})")
            new_image, response = await self.cog.submit_request(ctx, self.request)
            new_image = File(new_image)
            embed = ImagenEmbed(author=self.author, model_name=self.model_name, api_response=response)

            # Update button state to reflect completion
            self.retry_button.label = "Complete"
            self.retry_button.style = ButtonStyle.success

            # Send new message with new embed
            response_message = await ctx.followup.send(
                embed=embed,
                view=ImagenView(self.bot, ctx.author, self.model_name, self.request),
                file=new_image,
            )
            if self.bot.get_cog("prompt-inspector") is not None:
                response_message.add_reaction("🔍")
        except Exception as e:
            self.retry_button.disabled = True
            self.retry_button.label = "Failed!"
            self.retry_button.style = ButtonStyle.danger
            await ctx.followup.send(f"Retry failed: {e}", delete_after=30)
            logger.error(e)
        finally:
            await ctx.edit_original_response(view=self)
            return

    @ui.button(label="Delete", style=ButtonStyle.red)
    async def delete_button(self, button: ui.Button, ctx: MessageInteraction) -> None:
        await ctx.response.defer()
        self.retry_button.disabled = True
        self.delete_button.disabled = True
        self.delete_button.label = "Deleting..."
        self.delete_button.style = ButtonStyle.grey
        await ctx.message.edit(view=self)
        await ctx.message.delete(delay=1.0)
        await ctx.send("Message queued for deletion.", ephemeral=True, delete_after=30)
