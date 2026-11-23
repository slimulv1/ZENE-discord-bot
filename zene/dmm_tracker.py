#!/usr/bin/python
import asyncio
import json
from io import BytesIO
from pathlib import Path

import discord
import requests
from deep_translator import GoogleTranslator
from discord.ext import commands
from PIL import Image, ImageFilter

import dmm


def _first_actress(payload):
    try:
        items = payload.get("result", {}).get("actress", [])
        return items[0] if items else None
    except (AttributeError, TypeError, IndexError):
        return None


def _first_item(payload):
    """Return the first DMM item, or None for empty/unexpected payloads."""
    try:
        items = payload.get("result", {}).get("items", [])
        return items[0] if items else None
    except (AttributeError, TypeError, IndexError):
        return None


async def _translate(translator, text):
    """deep-translator is blocking — keep it off the event loop."""
    return await asyncio.to_thread(translator.translate, str(text))


def _credentials(bot):
    """Prefer env-backed Config; keep the legacy file only as a migration path."""
    config = getattr(bot, "config", None)
    if config is not None:
        return config.dmm_api_id, config.dmm_affiliate_id
    path = Path(__file__).resolve().parent / "TOKEN.json"
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return "", ""
    return data.get("DMM_API_ID", ""), data.get("DMM_AFFILIATE_ID", "")


class dmm_tracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def code(self, ctx, *, arg: str):
        if "-" in arg:
            arg = arg.replace("-", "00")

        api_id, affiliate_id = _credentials(self.bot)

        api = dmm.API(api_id=api_id, affiliate_id=affiliate_id)

        item_search = await asyncio.wait_for(
            asyncio.to_thread(
                api.item_search, site="FANZA", service="digital", keyword=arg, output="json"
            ),
            timeout=15,
        )

        data = json.dumps(item_search)
        collect_data = json.loads(data)
        item = _first_item(collect_data)
        if item is None:
            await ctx.send("Không tìm thấy mã này trên DMM.")
            return

        product_title = item.get("title", "")
        affiliate_url = item.get("affiliateURL", "")
        volume = item.get("volume", "")
        image_url = (item.get("imageURL") or {}).get("large", "")
        makers = (item.get("iteminfo") or {}).get("maker") or [{}]
        mega = makers[0].get("name", "")
        date = item.get("date", "")
        product_id = item.get("product_id", "")

        actress_lst = []
        price_lst = []

        try:
            for price in item["prices"]["deliveries"]["delivery"][0:3]:
                price_lst.append(price["price"] + " JPY")
        except (KeyError, TypeError, IndexError):
            price_lst = ["None"]

        try:
            for actress_name in item["iteminfo"]["actress"]:
                actress_lst.append(f"**{actress_name['name']}**【{actress_name['ruby']}】")
        except (KeyError, TypeError, IndexError):
            actress_lst = ["None"]

        code_translator = GoogleTranslator(source="ja", target="vi")

        if not self.bot.config.nsfw_enabled or ctx.channel.is_nsfw():
            embed_Image = image_url

            code_embed = discord.Embed(
                color=discord.Colour.blurple(),
                title=product_id.upper(),
                # url = affiliate_url,
                description=f"[**{await _translate(code_translator, product_title)}**]({affiliate_url})",
                # description = ''.join(embed_description)
            )

            # code_embed.set_thumbnail(url = image_url)
            code_embed.add_field(name="Ai Đồ", value="\n".join(actress_lst))
            code_embed.add_field(name="Giá", value="\n".join(price_lst))
            # code_embed.add_field(name = 'Sample', value = f'[Sample]({sampleURL})')
            code_embed.set_image(url=embed_Image)
            code_embed.set_footer(text=f"{mega} {date} {volume} phút")

            await ctx.send(embed=code_embed)

        else:

            def _blur_in_thread():
                response = requests.get(image_url, timeout=10)
                response.raise_for_status()
                with Image.open(BytesIO(response.content)) as img:
                    blurred = img.filter(ImageFilter.BoxBlur(10))
                output = BytesIO()
                blurred.save(output, format="JPEG")
                output.seek(0)
                return output

            # In-memory output: no shared simBlurImage.jpg race condition.
            output = await asyncio.to_thread(_blur_in_thread)
            file = discord.File(output, filename="image.png")
            embed_Image = "attachment://image.png"

            code_embed = discord.Embed(
                color=discord.Colour.blurple(),
                title=product_id.upper(),
                # url = affiliate_url,
                description=f"[**{await _translate(code_translator, product_title)}**]({affiliate_url})",
                # description = ''.join(embed_description)
            )

            # code_embed.set_thumbnail(url = image_url)
            code_embed.add_field(name="Ai Đồ", value="\n".join(actress_lst))
            code_embed.add_field(name="Giá", value="\n".join(price_lst))
            # code_embed.add_field(name = 'Sample', value = f'[Sample]({sampleURL})')
            code_embed.set_image(url=embed_Image)
            code_embed.set_footer(text=f"{mega} {date} {volume} phút")

            await ctx.send(file=file, embed=code_embed)

    @commands.command()
    async def idol(self, ctx, *, arg: str):
        if "-" in arg:
            arg = arg.replace("-", "00")

        api_id, affiliate_id = _credentials(self.bot)

        api = dmm.API(api_id=api_id, affiliate_id=affiliate_id)

        actress_search = await asyncio.wait_for(
            asyncio.to_thread(api.actress_search, site="FANZA", keyword=arg, output="json"),
            timeout=15,
        )

        data = json.dumps(actress_search)
        collect_data = json.loads(data)
        actress = _first_actress(collect_data)
        if actress is None:
            await ctx.send("Không tìm thấy diễn viên này trên DMM.")
            return

        actress_name = actress["name"]
        actress_ruby = actress["ruby"]
        actress_digitalURL = actress["listURL"]["digital"]
        bust = actress["bust"]
        waist = actress["waist"]
        hip = actress["hip"]
        height = actress["height"]
        birthday = actress["birthday"]
        hobby = actress["hobby"]
        birthplace = actress["prefectures"]
        imageURL = actress["imageURL"]["large"]

        bust_cup = actress.get("cup", "")

        idol_translator = GoogleTranslator(source="ja", target="vi")

        idol_embed = discord.Embed(
            color=discord.Colour.brand_green(),
            title=actress_name + f"【{actress_ruby}】",
            url=actress_digitalURL,
            description="Đến từ " + str(await _translate(idol_translator, birthplace)),
        )

        idol_embed.set_thumbnail(url=imageURL)
        idol_embed.add_field(name="Số đo 3 vòng", value=f"{bust} {waist} {hip} **{bust_cup}**")
        idol_embed.add_field(name="Chiều cao", value=height)
        idol_embed.add_field(name="Ngày sinh", value=birthday)
        idol_embed.add_field(name="Sở thích", value=await _translate(idol_translator, hobby))
        await ctx.send(embed=idol_embed)


async def setup(bot):
    await bot.add_cog(dmm_tracker(bot))
