import asyncio
from playwright.async_api import async_playwright
from datetime import datetime
import os
import shutil
import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials
import re

# Configurações de Ambiente
DOWNLOAD_DIR = "/tmp" 
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
IS_GITHUB = os.getenv("GITHUB_ACTIONS") == "true"

async def main():
    async with async_playwright() as p:
        # Lançamento do navegador com tolerância a lentidão (image_8d26ad)
        browser = await p.chromium.launch(headless=IS_GITHUB)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()
        
        # Aumenta o timeout padrão para 90s para evitar erros como os das imagens 8caf07 e 8cbac0
        page.set_default_timeout(90000) 

        try:
            print(f"🔐 Iniciando Login... (GitHub: {IS_GITHUB})")
            # Uso de networkidle para garantir que a página carregue totalmente (image_971b8e)
            await page.goto("https://spx.shopee.com.br/", wait_until="networkidle", timeout=120000)
            
            await page.locator('input[placeholder*="Ops ID"]').fill('Ops134294')
            await page.locator('input[placeholder*="Senha"]').fill('@Shopee123')
            
            # Clique de Login via JS para evitar travamentos de interface (image_8d26ad)
            login_btn = page.locator('button:has-text("Login"), .ant-btn-primary').first
            await login_btn.evaluate("el => el.click()")
            
            await page.wait_for_timeout(20000)
            await page.keyboard.press("Escape")

            print("🚚 Acessando aba de Viagens...")
            await page.goto("https://spx.shopee.com.br/#/hubLinehaulTrips/trip")
            await page.wait_for_timeout(10000)
            
            # Filtro Handedover via XPath (conforme log de sucesso na image_8c3ae1)
            print("🔍 Aplicando filtro...")
            xpath_filtro = "xpath=/html/body/div/div/div[2]/div[2]/div/div/div/div[2]/div[1]/div[1]/div/div[1]/div/div/div/div/div[3]/span"
            await page.locator(xpath_filtro).first.evaluate("el => el.click()")
            await page.wait_for_timeout(5000)

            print("📤 Solicitando Exportação...")
            await page.get_by_role("button", name=re.compile(r"Exportar|Export", re.I)).first.evaluate("el => el.click()")
            await page.wait_for_timeout(15000)

            print("📂 Navegando para o centro de tarefas...")
            await page.goto("https://spx.shopee.com.br/#/taskCenter/exportTaskCenter")
            await page.wait_for_timeout(15000)

            # Clique em Export Task para limpar possíveis pop-ups (image_8bd549)
            try: await page.locator("text='Export Task'").first.evaluate("el => el.click()")
            except: pass

            print("⬇️ Iniciando tentativa de download...")
            # Seletor híbrido para suportar "Baixar" ou "Download" (image_8cbe49)
            btn_download = page.locator("text='Baixar', text='Download'").first
            
            async with page.expect_download(timeout=120000) as download_info:
                # O evaluate ignora o erro "waiting for locator to be visible" (image_8caf07)
                await btn_download.evaluate("el => el.click()")
                print("✅ Comando de download disparado.")

            download = await download_info.value
            path = os.path.join(DOWNLOAD_DIR, download.suggested_filename)
            await download.save_as(path)
            print(f"🎉 Arquivo baixado: {download.suggested_filename}")

            # [Inserir aqui sua lógica de renomear e subir para o Sheets]

        except Exception as e:
            print(f"❌ Erro Crítico: {e}")
            if not IS_GITHUB: await page.screenshot(path="debug_shopee.png")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
