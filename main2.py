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

def rename_downloaded_file_handover(download_dir, download_path):
    try:
        current_hour = datetime.now().strftime("%H")
        new_file_name = f"PROD-{current_hour}.csv"
        new_file_path = os.path.join(download_dir, new_file_name)
        if os.path.exists(new_file_path):
            os.remove(new_file_path)
        shutil.move(download_path, new_file_path)
        print(f"Arquivo Handedover salvo como: {new_file_path}")
        return new_file_path
    except Exception as e:
        print(f"Erro ao renomear o arquivo Handedover: {e}")
        return None

def update_packing_google_sheets_handover(csv_file_path):
    try:
        if not os.path.exists(csv_file_path):
            print(f"Arquivo Handedover {csv_file_path} não encontrado.")
            return
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name("hxh.json", scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_url(
            "https://docs.google.com/spreadsheets/d/1LZ8WUrgN36Hk39f7qDrsRwvvIy1tRXLVbl3-wSQn-Pc/edit#gid=734921183"
        )
        worksheet = sheet.worksheet("Base Handedover")
        df = pd.read_csv(csv_file_path).fillna("")
        worksheet.clear()
        worksheet.update([df.columns.values.tolist()] + df.values.tolist())
        print("✅ Arquivo Handedover enviado com sucesso para a aba 'Base Handedover'.")
    except Exception as e:
        print(f"❌ Erro durante o upload Handedover: {e}")

async def main():
    async with async_playwright() as p:
        # No GitHub Actions, headless deve ser True para economizar recursos
        is_github = os.getenv("GITHUB_ACTIONS") == "true"
        browser = await p.chromium.launch(headless=is_github)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()
        
        # Aumenta timeout para 90s para lidar com lentidão da Shopee (imagem 97988a)
        page.set_default_timeout(90000) 

        try:
            print("🔐 Fazendo login no SPX (Ops134294)...")
            await page.goto("https://spx.shopee.com.br/", wait_until="networkidle")
            
            # Login com seletores mais flexíveis
            await page.locator('input[placeholder*="Ops ID"]').fill('Ops134294')
            await page.locator('input[placeholder*="Senha"]').fill('@Shopee123')
            
            # Clique via evaluate para ignorar elementos sobrepostos (imagem 971b8e)
            login_btn = page.locator('button:has-text("Login"), .ant-btn-primary').first
            await login_btn.evaluate("el => el.click()")
            
            print("⏳ Aguardando estabilização pós-login...")
            await page.wait_for_timeout(15000)
            await page.keyboard.press("Escape")

            # Tratamento de Pop-ups (Script 2 aprimorado)
            print("🧹 Limpando possíveis pop-ups...")
            possible_closes = [".ssc-dialog-close", ".ant-modal-close", "[aria-label='Close']"]
            for btn in possible_closes:
                if await page.locator(btn).count() > 0:
                    await page.locator(btn).first.evaluate("el => el.click()")

            print("\n🚚 Indo para a página de viagens...")
            await page.goto("https://spx.shopee.com.br/#/hubLinehaulTrips/trip")
            await page.wait_for_timeout(10000)

            print("🔍 Aplicando filtro 'Handedover'...")
            # XPath aprimorado para ser menos sensível a mudanças leves de DOM
            handedover_xpath = "//span[contains(text(), 'Handedover')]"
            try:
                await page.locator(handedover_xpath).first.evaluate("el => el.click()")
            except:
                await page.get_by_text("Handedover").first.click(force=True)
                
            print("✅ Filtro 'Handedover' acionado.")
            await page.wait_for_timeout(10000)

            print("📤 Solicitando Exportação...")
            # Suporte bilíngue para o botão Exportar (imagem 8cbe49)
            await page.get_by_role("button", name=re.compile(r"Exportar|Export", re.I)).first.evaluate("el => el.click()")
            await page.wait_for_timeout(15000)

            print("📂 Indo para o centro de tarefas...")
            await page.goto("https://spx.shopee.com.br/#/taskCenter/exportTaskCenter")
            await page.wait_for_timeout(15000)

            # Garante que a aba correta está focada
            try:
                await page.get_by_text(re.compile(r"Exportar tarefa|Export Task", re.I)).first.click()
                await page.wait_for_timeout(5000)
            except: pass

            print("⬇️ Iniciando download...")
            # Busca por 'Baixar' ou 'Download' para evitar erro da imagem 8caf07
            btn_download = page.locator("text='Baixar', text='Download'").first
            
            async with page.expect_download(timeout=120000) as download_info:
                await btn_download.evaluate("el => el.click()")

            download = await download_info.value
            download_path = os.path.join(DOWNLOAD_DIR, download.suggested_filename)
            await download.save_as(download_path)
            print(f"✅ Download concluído: {download_path}")

            new_file_path = rename_downloaded_file_handover(DOWNLOAD_DIR, download_path)
            if new_file_path:
                update_packing_google_sheets_handover(new_file_path)

            print("\n🎉 PROCESSO CONCLUÍDO COM SUCESSO!")

        except Exception as e:
            print(f"❌ Erro crítico: {e}")
            # Tira print do erro no GitHub Actions para facilitar o debug
            await page.screenshot(path="debug_error.png")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
