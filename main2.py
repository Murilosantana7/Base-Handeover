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
# Funções de Apoio (Mantidas simples)
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

            # 2. TRATAMENTO DE POP-UP (CÓPIA DO PENDING)
            # Esse bloco funcionou no seu outro script, então trouxemos ele de volta
            log("⏳ Aguardando renderização do pop-up (10s)...")
            await page.wait_for_timeout(10000) 
            
            popup_closed = False
            # Tentativa 1: ESC
            try:
                await page.keyboard.press("Escape")
            except: pass
            
            # Tentativa 2: Seletores Específicos (Do Pending)
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
            
            # Tentativa 3: Máscara/Fundo (Do Pending)
            if not popup_closed:
                masks = [".ant-modal-mask", ".ssc-dialog-mask", ".ssc-modal-mask"]
                for mask in masks:
                    if await page.locator(mask).count() > 0:
                        try:
                            await page.locator(mask).first.click(position={"x": 10, "y": 10}, force=True)
                            break
                        except: pass
            
            # Limpeza Extra de Garantia (Minha adição de segurança)
            await page.evaluate('''() => {
                document.querySelectorAll('.ssc-dialog-wrapper, .ssc-dialog-mask').forEach(el => el.remove());
            }''')

            # 3. NAVEGAÇÃO E EXPORTAÇÃO (Adaptação necessária para Handedover)
            log("🚚 Indo para Viagens...")
            await page.goto("https://spx.shopee.com.br/#/hubLinehaulTrips/trip")
            await page.wait_for_timeout(12000)

            # [DIFERENÇA] Aqui precisamos clicar no Handedover
            log("🔍 Filtrando Handedover...")
            try:
                # Usamos o evaluate (igual ao clique de download do Pending) para garantir
                await page.get_by_text("Handedover").first.evaluate("element => element.click()")
            except: pass
            
            await page.wait_for_timeout(3000)
            
            log("📤 Clicando em exportar...")
            # Usando evaluate para evitar bloqueio de pop-up residual
            await page.get_by_role("button", name="Exportar").first.evaluate("element => element.click()")
            await page.wait_for_timeout(12000)

            # 4. CENTRO DE TAREFAS (CÓPIA DO PENDING)
            log("📂 Indo para o centro de tarefas...")
            await page.goto("https://spx.shopee.com.br/#/taskCenter/exportTaskCenter")
            await page.wait_for_timeout(10000)
            
            # Seleção de Aba (Do Pending)
            try:
                await page.get_by_text("Exportar tarefa").or_(page.get_by_text("Export Task")).click(force=True, timeout=5000)
            except: pass

            # 5. LÓGICA DE ESPERA (CÓPIA DO PENDING + LOOP)
            # O Pending espera 20s pelo texto. Vamos fazer isso dentro de um loop.
            log("⬇️ Aguardando a tabela carregar...")
            
            download_sucesso = False
            for i in range(1, 15): # Tenta por várias vezes
                try:
                    # AQUI ESTÁ A CHAVE: O Pending usa wait_for_selector com timeout longo.
                    # Isso faz o script "sentar e esperar" a tabela aparecer, em vez de recarregar freneticamente.
                    log(f"⏳ Tentativa {i}: Procurando texto 'Baixar' (Aguardando até 20s)...")
                    await page.wait_for_selector("text=Baixar", timeout=20000)
                    
                    log("✅ Texto 'Baixar' encontrado! Iniciando download...")
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
                    # Se não apareceu em 20 segundos, aí sim damos refresh
                    log("⚠️ Arquivo ainda não pronto. Recarregando...")
                    await page.reload()
                    await page.wait_for_load_state("networkidle")
                    # Re-foca a aba (importante após reload)
                    try:
                        await page.get_by_text("Exportar tarefa").or_(page.get_by_text("Export Task")).click(force=True, timeout=5000)
                    except: pass
            
            if not download_sucesso: log("❌ Timeout Final.")

        except Exception as e:
            log(f"❌ Erro fatal: {e}")
            await page.screenshot(path="debug_pending_style.png", full_page=True)
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())