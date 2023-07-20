import logging
from io import BytesIO
from pathlib import Path
from typing import Optional

from disnake import (
    ButtonStyle,
    File,
    MessageInteraction,
)
from disnake.ui import Button, View, button

logger = logging.getLogger(__name__)


class PromptView(View):
    def __init__(self, metadata: str, filename: Optional[str] = None, timeout: float = 3600.0):
        super().__init__(timeout=timeout)
        self.metadata: Optional[str] = metadata
        self.filename: Optional[str] = filename

    @button(label="Raw Metadata", style=ButtonStyle.blurple, custom_id="prompt_inspector:raw_metadata")
    async def details(self, button: Button, ctx: MessageInteraction):
        await ctx.response.defer()
        try:
            button.disabled = True
            button.label = "✅ Done"
            button.style = ButtonStyle.green

            if len(self.metadata) > 1980:
                metafile_name = (
                    Path(self.filename).with_suffix(".txt").name
                    if self.filename is not None
                    else "metadata.txt"
                )
                metadata_file = BytesIO(self.metadata.encode("utf-8"))
                attachment = File(metadata_file, filename=metafile_name)
                await ctx.send(content="Metadata won't fit in message, see attached file", file=attachment)
            else:
                await ctx.send(f"```csv\n{self.metadata}```")

        except Exception as e:
            await ctx.followup.send(f"Sending details failed: {e}")
            button.disabled = True
            button.label = "❌ Failed"
            button.style = ButtonStyle.red
            logger.error(e)
        finally:
            await ctx.edit_original_response(view=self)
            return
