import asyncio
from playwright.async_api import async_playwright
from datetime import datetime
import os
import shutil
import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials
import re

# Configuração de Ambiente
DOWNLOAD_DIR = "/tmp" 
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
IS_GITHUB = os.getenv("GITHUB_ACTIONS") == "true"

async def main():
    async with async_playwright() as p:
        # Lança o navegador com timeout estendido para conexões lentas
        browser = await p.chromium.launch(headless=IS_GITHUB)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()
        
        # Aumenta o timeout padrão para 90 segundos devido à lentidão vista na imagem 8d26ad
        page.set_default_timeout(90000) 

        try:
            print(f"🔐 Iniciando Login... (GitHub: {IS_GITHUB})")
            await page.goto("https://spx.shopee.com.br/", wait_until="networkidle", timeout=120000)
            
            # Preenchimento de credenciais
            await page.locator('input[placeholder*="Ops ID"]').fill('Ops134294')
            await page.locator('input[placeholder*="Senha"]').fill('@Shopee123')
            
            # Clique de Login (Usando seletor da imagem 971b8e com espera forçada)
            login_btn = page.locator('button:has-text("Login"), .ant-btn-primary').first
            await login_btn.wait_for(state="attached") # Espera existir no código
            await login_btn.evaluate("el => el.click()") # Clica ignorando se está visível
            
            print("⏳ Aguardando estabilização pós-login...")
            await page.wait_for_timeout(20000)
            await page.keyboard.press("Escape")

            # Navegação para Viagens
            print("🚚 Acessando Viagens...")
            await page.goto("https://spx.shopee.com.br/#/hubLinehaulTrips/trip")
            await page.wait_for_timeout(10000)
            
            # Filtro Handedover (conforme XPath da imagem 8bbb84)
            print("🔍 Aplicando filtro Handedover...")
            xpath_filtro = "xpath=/html/body/div/div/div[2]/div[2]/div/div/div/div[2]/div[1]/div[1]/div/div[1]/div/div/div/div/div[3]/span"
            await page.locator(xpath_filtro).first.evaluate("el => el.click()")
            await page.wait_for_timeout(5000)

            # Exportação
            print("📤 Solicitando Exportação...")
            await page.get_by_role("button", name=re.compile(r"Exportar|Export", re.I)).first.evaluate("el => el.click()")
            await page.wait_for_timeout(15000)

            # Centro de Tarefas e Download
            print("📂 Navegando para Centro de Tarefas...")
            await page.goto("https://spx.shopee.com.br/#/taskCenter/exportTaskCenter")
            await page.wait_for_timeout(10000)

            # Limpeza visual (conforme imagem 8c3ae1)
            try: await page.locator("text='Export Task'").first.evaluate("el => el.click()")
            except: pass

            print("⬇️ Tentando capturar download...")
            # Seletor duplo para evitar erro de idioma (imagem 8cbe49)
            btn_download = page.locator("text='Baixar', text='Download'").first
            
            async with page.expect_download(timeout=120000) as download_info:
                await btn_download.evaluate("el => el.click()")
                print("✅ Clique de download executado.")

            download = await download_info.value
            path = os.path.join(DOWNLOAD_DIR, download.suggested_filename)
            await download.save_as(path)
            
            # Lógica de salvar e subir (Resumida para o exemplo)
            print(f"🎉 Download concluído: {download.suggested_filename}")

        except Exception as e:
            print(f"❌ Falha Crítica Detectada: {e}")
            # Tira print do erro para debug se não for no GitHub
            if not IS_GITHUB: await page.screenshot(path="erro_debug.png")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
