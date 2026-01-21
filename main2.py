import asyncio
from playwright.async_api import async_playwright
from datetime import datetime
import os
import shutil
import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials
import time

DOWNLOAD_DIR = "/tmp"

# ==============================
# Funções de Apoio
# ==============================
def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def rename_downloaded_file_handover(download_dir, download_path):
    try:
        current_hour = datetime.now().strftime("%H")
        new_file_name = f"PROD-{current_hour}.csv"
        new_file_path = os.path.join(download_dir, new_file_name)
        if os.path.exists(new_file_path): os.remove(new_file_path)
        shutil.move(download_path, new_file_path)
        log(f"✅ Arquivo salvo: {new_file_name}")
        return new_file_path
    except Exception: return None

def update_google_sheets_handover(csv_file_path):
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name("hxh.json", scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_url("https://docs.google.com/spreadsheets/d/1LZ8WUrgN36Hk39f7qDrsRwvvIy1tRXLVbl3-wSQn-Pc/edit#gid=734921183")
        worksheet = sheet.worksheet("Base Handedover")
        df = pd.read_csv(csv_file_path).fillna("")
        worksheet.clear()
        worksheet.update([df.columns.values.tolist()] + df.values.tolist())
        log(f"✅ Sheets atualizada!")
    except Exception: pass

# ==============================
# Fluxo Principal (Estrutura do Pending)
# ==============================
async def main():
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    async with async_playwright() as p:
        # Configuração idêntica ao Pending
        browser = await p.chromium.launch(headless=True)
        # Viewport maior ajuda a evitar elementos sobrepostos
        context = await browser.new_context(accept_downloads=True, viewport={'width': 1366, 'height': 768})
        page = await context.new_page()

        try:
            # 1. LOGIN (CÓPIA DO PENDING)
            log("🔐 Fazendo login no SPX...")
            await page.goto("https://spx.shopee.com.br/")
            await page.wait_for_selector('xpath=//*[@placeholder="Ops ID"]', timeout=10000)
            await page.locator('xpath=//*[@placeholder="Ops ID"]').fill('Ops134294')
            await page.locator('xpath=//*[@placeholder="Senha"]').fill('@Shopee123')
            await page.locator('xpath=/html/body/div[1]/div/div[2]/div/div/div[1]/div[3]/form/div/div/button').click()
            await page.wait_for_load_state("networkidle", timeout=40000)

            # 2. TRATAMENTO DE POP-UP (CÓPIA EXATA DO PENDING)
            log("⏳ Aguardando renderização do pop-up (10s)...")
            await page.wait_for_timeout(10000) 
            
            popup_closed = False
            # Tentativa 1: ESC
            try:
                await page.keyboard.press("Escape")
            except: pass
            
            # Tentativa 2: Botões de fechar (Lista do Pending)
            possible_buttons = [
                ".ssc-dialog-header .ssc-dialog-close-icon-wrapper",
                ".ssc-dialog-close-icon-wrapper",
                "svg.ssc-dialog-close",             
                ".ant-modal-close",                
                ".ant-modal-close-x",
                "[aria-label='Close']"
            ]
            for selector in possible_buttons:
                if await page.locator(selector).count() > 0:
                    try:
                        await page.locator(selector).first.evaluate("element => element.click()")
                        popup_closed = True
                        break
                    except: pass
            
            # Tentativa 3: Máscara/Fundo (Lista do Pending)
            if not popup_closed:
                masks = [".ant-modal-mask", ".ssc-dialog-mask", ".ssc-modal-mask"]
                for mask in masks:
                    if await page.locator(mask).count() > 0:
                        try:
                            await page.locator(mask).first.click(position={"x": 10, "y": 10}, force=True)
                            break
                        except: pass
            
            # 3. NAVEGAÇÃO E EXPORTAÇÃO
            log("🚚 Indo para Viagens...")
            await page.goto("https://spx.shopee.com.br/#/hubLinehaulTrips/trip")
            await page.wait_for_timeout(10000)

            # [DIFERENÇA NECESSÁRIA] Filtrar Handedover
            log("🔍 Filtrando Handedover...")
            try:
                # Clica usando JS para garantir, caso ainda tenha algum overlay
                await page.get_by_text("Handedover").first.evaluate("element => element.click()")
            except: pass
            
            await page.wait_for_timeout(3000)
            
            log("📤 Clicando em exportar...")
            await page.get_by_role("button", name="Exportar").first.evaluate("element => element.click()")
            await page.wait_for_timeout(12000)

            # 4. CENTRO DE TAREFAS (CÓPIA DO PENDING)
            log("📂 Indo para o centro de tarefas...")
            await page.goto("https://spx.shopee.com.br/#/taskCenter/exportTaskCenter")
            
            # Espera a aba aparecer antes de clicar
            try:
                await page.wait_for_selector("text=Exportar tarefa", timeout=15000)
                await page.get_by_text("Exportar tarefa").or_(page.get_by_text("Export Task")).click(force=True)
            except: pass

            # 5. DOWNLOAD (ESTRUTURA DO PENDING + LOOP)
            # O Pending espera 20s. Vamos fazer isso num loop eficiente.
            log("⬇️ Aguardando tabela...")
            
            download_sucesso = False
            for i in range(1, 15): 
                try:
                    # O segredo do Pending: esperar o SELETOR aparecer
                    log(f"⏳ Tentativa {i}: Procurando texto 'Baixar' (até 10s)...")
                    await page.wait_for_selector("text=Baixar", timeout=10000)
                    
                    log("✅ Botão encontrado! Clicando via JS...")
                    async with page.expect_download(timeout=60000) as download_info:
                        # CLIQUE VIA JS (IGUAL AO PENDING)
                        await page.locator("text=Baixar").first.evaluate("element => element.click()")
                    
                    download = await download_info.value
                    path = os.path.join(DOWNLOAD_DIR, download.suggested_filename)
                    await download.save_as(path)
                    
                    final = rename_downloaded_file_handover(DOWNLOAD_DIR, path)
                    if final: update_google_sheets_handover(final)
                    download_sucesso = True
                    break
                
                except Exception:
                    # Se não apareceu em 10s, recarrega
                    log("⚠️ Arquivo não pronto. Recarregando...")
                    await page.reload()
                    await page.wait_for_load_state("networkidle")
                    try:
                        await page.get_by_text("Exportar tarefa").or_(page.get_by_text("Export Task")).click(force=True)
                    except: pass
            
            if not download_sucesso: log("❌ Timeout Final.")

        except Exception as e:
            log(f"❌ Erro fatal: {e}")
            await page.screenshot(path="debug_pending_copy.png", full_page=True)
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
