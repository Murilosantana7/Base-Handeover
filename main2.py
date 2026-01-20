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

def log(mensagem):
    horario = datetime.now().strftime("%H:%M:%S")
    print(f"[{horario}] {mensagem}")

# Função de limpeza reutilizável (A CHAVE PARA RESOLVER O PROBLEMA)
async def limpar_popups(page):
    log("🧹 Varrendo e destruindo pop-ups bloqueadores...")
    try:
        await page.evaluate('''() => {
            // Remove modais, máscaras e wrappers de diálogo
            const seletores = [
                '.ssc-dialog-wrapper', 
                '.ssc-dialog-mask', 
                '.ant-modal-mask', 
                '.ant-modal-wrap',
                '.ssc-dialog' // Adicionado para garantir
            ];
            seletores.forEach(s => document.querySelectorAll(s).forEach(el => el.remove()));
            document.body.style.overflow = 'auto'; // Destrava o scroll
        }''')
        # Tenta fechar com ESC apenas por garantia
        await page.keyboard.press("Escape")
    except Exception as e:
        log(f"⚠️ Aviso na limpeza: {e}")

def rename_downloaded_file_handover(download_dir, download_path):
    try:
        current_hour = datetime.now().strftime("%H")
        new_file_name = f"PROD-{current_hour}.csv"
        new_file_path = os.path.join(download_dir, new_file_name)
        if os.path.exists(new_file_path): os.remove(new_file_path)
        shutil.move(download_path, new_file_path)
        log(f"✅ Arquivo renomeado: {new_file_name}")
        return new_file_path
    except Exception as e:
        log(f"❌ Erro ao renomear: {e}")
        return None

def update_google_sheets_handover(csv_file_path):
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name("hxh.json", scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_url("https://docs.google.com/spreadsheets/d/1LZ8WUrgN36Hk39f7qDrsRwvvIy1tRXLVbl3-wSQn-Pc/edit#gid=734921183")
        worksheet = sheet.worksheet("Base Handedover")
        
        log("📊 Lendo CSV...")
        df = pd.read_csv(csv_file_path).fillna("")
        
        log("📤 Atualizando Sheets...")
        worksheet.clear()
        worksheet.update([df.columns.values.tolist()] + df.values.tolist())
        log("✅ Sucesso!")
    except Exception as e:
        log(f"❌ Erro no Sheets: {e}")

async def main():
    start_time = time.time()
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    
    async with async_playwright() as p:
        log("🚀 Iniciando...")
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(accept_downloads=True, viewport={'width': 1366, 'height': 768})
        page = await context.new_page()

        try:
            # 1. LOGIN
            log("🔐 Login...")
            await page.goto("https://spx.shopee.com.br/")
            await page.wait_for_selector('xpath=//*[@placeholder="Ops ID"]', timeout=15000)
            await page.locator('xpath=//*[@placeholder="Ops ID"]').fill('Ops134294')
            await page.locator('xpath=//*[@placeholder="Senha"]').fill('@Shopee123')
            await page.locator('button:has-text("Login"), button:has-text("Entrar")').click()
            await page.wait_for_load_state("networkidle")

            # Limpeza Pós-Login
            await page.wait_for_timeout(5000)
            await limpar_popups(page)

            # 2. NAVEGAÇÃO PARA VIAGENS (Aqui estava o ponto cego)
            log("🚚 Indo para Viagens...")
            await page.goto("https://spx.shopee.com.br/#/hubLinehaulTrips/trip")
            await page.wait_for_timeout(8000) 
            
            # === LIMPEZA CRÍTICA AQUI ===
            # O pop-up "Datafix Tool" aparece ao carregar ESSA página. Precisamos matar ele agora.
            await limpar_popups(page)
            # ============================

            log("🔍 Filtrando Handedover...")
            # Agora o caminho deve estar livre, mas mantemos o evaluate por segurança
            await page.get_by_text("Handedover").first.evaluate("element => element.click()")
            await page.wait_for_timeout(3000)
            
            log("📤 Exportando...")
            # O botão exportar agora deve estar "clicável" pois removemos o overlay
            exportar_btn = page.get_by_role("button", name="Exportar").first
            await exportar_btn.evaluate("element => element.click()")
            await page.wait_for_timeout(8000)

            # 3. CENTRO DE TAREFAS
            log("📂 Indo para Centro de Tarefas...")
            await page.goto("https://spx.shopee.com.br/#/taskCenter/exportTaskCenter")
            await page.wait_for_timeout(7000)
            
            # Limpeza preventiva também no Centro de Tarefas
            await limpar_popups(page)

            try:
                # Tenta focar na aba
                aba = page.get_by_text("Exportar tarefa").or_(page.get_by_text("Export Task")).first
                if await aba.is_visible():
                    await aba.evaluate("element => element.click()")
            except: pass

            # 4. DOWNLOAD
            log("⬇️ Buscando download...")
            download_ok = False
            for i in range(1, 15):
                baixar_btn = page.locator('text="Baixar"').first
                
                if await baixar_btn.is_visible():
                    log(f"✨ Botão encontrado!")
                    try:
                        async with page.expect_download(timeout=60000) as download_info:
                            await baixar_btn.evaluate("element => element.click()")
                        
                        download = await download_info.value
                        path = os.path.join(DOWNLOAD_DIR, download.suggested_filename)
                        await download.save_as(path)
                        
                        final = rename_downloaded_file_handover(DOWNLOAD_DIR, path)
                        if final: update_google_sheets_handover(final)
                        download_ok = True
                        break
                    except: pass
                
                log(f"⏳ Tentativa {i}: Recarregando...")
                await page.wait_for_timeout(10000)
                await page.reload()
                await page.wait_for_load_state("domcontentloaded")
                # Re-limpa popups após reload e re-foca aba
                await limpar_popups(page)
                try:
                    aba = page.get_by_text("Exportar tarefa").or_(page.get_by_text("Export Task")).first
                    await aba.evaluate("element => element.click()")
                except: pass

            if not download_ok: log("❌ Timeout.")
            log(f"🎉 Tempo total: {round(time.time() - start_time)}s")

        except Exception as e:
            log(f"❌ ERRO: {e}")
            await page.screenshot(path="debug_error.png", full_page=True)
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())