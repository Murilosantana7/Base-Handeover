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

# Configuração das Bases que serão baixadas
# (Nome do Filtro na Shopee, Nome da Aba no Google Sheets, Prefixo do Arquivo)
LISTA_DE_BASES = [
    {"filtro": "Handedover", "aba_sheets": "Base Handedover", "prefixo": "PROD"},
    {"filtro": "Expedidos",  "aba_sheets": "Base Expedidos",  "prefixo": "EXP"} 
    # Obs: Se na Shopee estiver em inglês, o script tenta "Shipped" automaticamente para Expedidos.
]

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def rename_file(download_dir, download_path, prefixo):
    try:
        current_hour = datetime.now().strftime("%H")
        new_file_name = f"{prefixo}-{current_hour}.csv"
        new_file_path = os.path.join(download_dir, new_file_name)
        if os.path.exists(new_file_path): os.remove(new_file_path)
        shutil.move(download_path, new_file_path)
        log(f"✅ Arquivo salvo: {new_file_name}")
        return new_file_path
    except Exception: return None

def update_google_sheets(csv_file_path, nome_aba):
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name("hxh.json", scope)
        client = gspread.authorize(creds)
        # ID da planilha mantido
        sheet = client.open_by_url("https://docs.google.com/spreadsheets/d/1LZ8WUrgN36Hk39f7qDrsRwvvIy1tRXLVbl3-wSQn-Pc/edit#gid=734921183")
        
        # Verifica se a aba existe, senão cria (opcional, mas evita erro)
        try:
            worksheet = sheet.worksheet(nome_aba)
        except:
            log(f"⚠️ Aba '{nome_aba}' não encontrada. Tentando atualizar na aba padrão ou criar...")
            return

        df = pd.read_csv(csv_file_path).fillna("")
        worksheet.clear()
        worksheet.update([df.columns.values.tolist()] + df.values.tolist())
        log(f"✅ Aba '{nome_aba}' atualizada!")
    except Exception as e:
        log(f"❌ Erro no Sheets ({nome_aba}): {e}")

async def processar_exportacao(page, config):
    filtro = config["filtro"]
    aba = config["aba_sheets"]
    prefixo = config["prefixo"]

    log(f"🚀 --- INICIANDO PROCESSO: {filtro.upper()} ---")
    
    # 1. IR PARA VIAGENS
    log("🚚 Indo para Viagens...")
    await page.goto("https://spx.shopee.com.br/#/hubLinehaulTrips/trip")
    await page.wait_for_timeout(8000)

    # 2. APLICAR FILTRO
    log(f"🔍 Clicando no filtro '{filtro}'...")
    try:
        # Tenta o nome exato (Ex: Handedover) ou tradução comum (Ex: Expedidos ou Shipped)
        if filtro == "Expedidos":
            seletor_filtro = page.get_by_text("Expedidos").or_(page.get_by_text("Shipped")).first
        else:
            seletor_filtro = page.get_by_text(filtro).first
            
        await seletor_filtro.evaluate("element => element.click()")
    except Exception as e:
        log(f"⚠️ Não consegui clicar no filtro '{filtro}': {e}")
        return # Pula para o próximo se falhar o filtro

    await page.wait_for_timeout(3000)

    # 3. EXPORTAR
    log("📤 Solicitando Exportação...")
    try:
        await page.get_by_role("button", name="Exportar").first.evaluate("element => element.click()")
    except:
        log("⚠️ Botão exportar não encontrado ou erro no clique.")
        return

    await page.wait_for_timeout(5000)

    # 4. CENTRO DE TAREFAS
    log("📂 Indo para Centro de Tarefas...")
    await page.goto("https://spx.shopee.com.br/#/taskCenter/exportTaskCenter")
    
    # Espera a aba aparecer
    try:
        await page.wait_for_selector("text=Exportar tarefa", timeout=10000)
        await page.get_by_text("Exportar tarefa").or_(page.get_by_text("Export Task")).click(force=True)
    except: pass

    # 5. DOWNLOAD (Lógica Pending)
    log(f"⬇️ Aguardando arquivo '{filtro}' ficar pronto...")
    download_sucesso = False
    
    for i in range(1, 15):
        try:
            # Espera o botão "Baixar" aparecer (TIMEOUT INTELIGENTE)
            await page.wait_for_selector("text=Baixar", timeout=10000)
            
            log(f"⚡ Botão Baixar apareceu! Baixando {filtro}...")
            async with page.expect_download(timeout=60000) as download_info:
                # Clica sempre no PRIMEIRO botão baixar (o mais recente)
                await page.locator("text=Baixar").first.evaluate("element => element.click()")
            
            download = await download_info.value
            path = os.path.join(DOWNLOAD_DIR, download.suggested_filename)
            await download.save_as(path)
            
            final_path = rename_file(DOWNLOAD_DIR, path, prefixo)
            if final_path:
                update_google_sheets(final_path, aba)
            
            download_sucesso = True
            break
        
        except Exception:
            log(f"⏳ Tentativa {i}: Arquivo {filtro} processando. Reload...")
            await page.reload()
            await page.wait_for_load_state("networkidle")
            # Re-foca na aba correta após reload
            try:
                await page.get_by_text("Exportar tarefa").or_(page.get_by_text("Export Task")).click(force=True)
            except: pass
    
    if not download_sucesso:
        log(f"❌ Timeout ao baixar {filtro}.")

async def main():
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(accept_downloads=True, viewport={'width': 1366, 'height': 768})
        page = await context.new_page()

        try:
            # === LOGIN (Uma única vez) ===
            log("🔐 Login...")
            await page.goto("https://spx.shopee.com.br/")
            await page.wait_for_selector('xpath=//*[@placeholder="Ops ID"]', timeout=10000)
            await page.locator('xpath=//*[@placeholder="Ops ID"]').fill('Ops134294')
            await page.locator('xpath=//*[@placeholder="Senha"]').fill('@Shopee123')
            await page.locator('xpath=/html/body/div[1]/div/div[2]/div/div/div[1]/div[3]/form/div/div/button').click()
            await page.wait_for_load_state("networkidle", timeout=40000)

            # === LIMPEZA INICIAL DE POPUPS ===
            log("🧹 Limpando pop-ups...")
            await page.wait_for_timeout(5000)
            try: await page.keyboard.press("Escape")
            except: pass
            await page.evaluate('''() => {
                document.querySelectorAll('.ssc-dialog-wrapper, .ssc-dialog-mask').forEach(el => el.remove());
            }''')

            # === LOOP PARA BAIXAR AS BASES ===
            for config in LISTA_DE_BASES:
                await processar_exportacao(page, config)

            log("🎉 TODOS OS PROCESSOS CONCLUÍDOS!")

        except Exception as e:
            log(f"❌ Erro Geral: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())