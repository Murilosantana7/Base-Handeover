import asyncio
from playwright.async_api import async_playwright
from datetime import datetime
import os
import shutil
import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials
import time

DOWNLOAD_DIR = "/tmp"  # No Windows, pode ser necessário ajustar (ex: "C:\\Users\\Murilo\\Downloads")

# Configuração das Bases
LISTA_DE_BASES = [
    {
        "filtro": "Handedover", 
        "aba_sheets": "Base Handedover", 
        "prefixo": "PROD",
        # XPath específico que você forneceu
        "xpath": "/html/body/div/div/div[2]/div[2]/div/div/div/div[1]/div[1]/div[1]/div/div[1]/div/div/div/div/div[3]/span"
    },
    {
        "filtro": "Expedidos",  
        "aba_sheets": "Base Expedidos",  
        "prefixo": "EXP",
        "xpath": None # Para Expedidos usamos o texto, pois não temos o XPath ainda
    } 
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
    except Exception as e:
        log(f"❌ Erro ao renomear: {e}")
        return None

def update_google_sheets(csv_file_path, nome_aba):
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name("hxh.json", scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_url("https://docs.google.com/spreadsheets/d/1LZ8WUrgN36Hk39f7qDrsRwvvIy1tRXLVbl3-wSQn-Pc/edit#gid=734921183")
        
        try:
            worksheet = sheet.worksheet(nome_aba)
        except:
            log(f"⚠️ Aba '{nome_aba}' não encontrada.")
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
    xpath_filtro = config["xpath"]

    log(f"🚀 --- INICIANDO PROCESSO: {filtro.upper()} ---")
    
    # 1. IR PARA VIAGENS
    log("🚚 Indo para Viagens...")
    await page.goto("https://spx.shopee.com.br/#/hubLinehaulTrips/trip")
    await page.wait_for_timeout(5000)

    # Limpeza preventiva
    await page.evaluate('''() => {
        document.querySelectorAll('.ssc-dialog-wrapper, .ssc-dialog-mask').forEach(el => el.remove());
    }''')

    # 2. APLICAR FILTRO
    log(f"🔍 Clicando no filtro '{filtro}'...")
    try:
        if xpath_filtro:
            # Se temos o XPath exato (Handedover), usamos ele
            seletor = page.locator(f"xpath={xpath_filtro}")
        elif filtro == "Expedidos":
            # Para Expedidos, mantemos a busca por texto
            seletor = page.get_by_text("Expedidos").or_(page.get_by_text("Shipped")).first
        else:
            seletor = page.get_by_text(filtro).first
            
        await seletor.highlight() # Mostra visualmente onde vai clicar
        await seletor.evaluate("element => element.click()")
    except Exception as e:
        log(f"⚠️ Erro ao clicar no filtro '{filtro}': {e}")
        return

    await page.wait_for_timeout(3000)

    # 3. EXPORTAR
    log("📤 Solicitando Exportação...")
    try:
        btn_export = page.get_by_role("button", name="Exportar").first
        await btn_export.highlight()
        await btn_export.evaluate("element => element.click()")
    except:
        log("⚠️ Botão exportar falhou.")
        return

    await page.wait_for_timeout(5000)

    # 4. CENTRO DE TAREFAS
    log("📂 Indo para Centro de Tarefas...")
    await page.goto("https://spx.shopee.com.br/#/taskCenter/exportTaskCenter")
    
    try:
        await page.wait_for_selector("text=Exportar tarefa", timeout=10000)
        await page.get_by_text("Exportar tarefa").or_(page.get_by_text("Export Task")).click(force=True)
    except: pass

    # 5. DOWNLOAD (Paciência de 60 segundos)
    log(f"⬇️ Aguardando arquivo '{filtro}' ficar pronto...")
    download_sucesso = False
    
    for i in range(1, 10):
        try:
            # Espera até 60 segundos pelo botão
            await page.wait_for_selector("text=Baixar", timeout=60000)
            
            log(f"⚡ Botão Baixar apareceu! Clicando...")
            async with page.expect_download(timeout=60000) as download_info:
                btn_baixar = page.locator("text=Baixar").first
                await btn_baixar.highlight()
                await btn_baixar.evaluate("element => element.click()")
            
            download = await download_info.value
            path = os.path.join(DOWNLOAD_DIR, download.suggested_filename)
            await download.save_as(path)
            
            final_path = rename_file(DOWNLOAD_DIR, path, prefixo)
            if final_path:
                update_google_sheets(final_path, aba)
            
            download_sucesso = True
            break
        
        except Exception:
            log(f"⏳ Tentativa {i}: Passou 1 minuto e não ficou pronto. Dando Reload...")
            await page.reload()
            await page.wait_for_load_state("networkidle")
            try:
                await page.get_by_text("Exportar tarefa").or_(page.get_by_text("Export Task")).click(force=True)
            except: pass
    
    if not download_sucesso:
        log(f"❌ Timeout ao baixar {filtro}.")

async def main():
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    async with async_playwright() as p:
        # headless=False para ver o navegador
        browser = await p.chromium.launch(headless=False, slow_mo=50) 
        context = await browser.new_context(accept_downloads=True, viewport={'width': 1366, 'height': 768})
        page = await context.new_page()

        try:
            log("🔐 Login...")
            await page.goto("https://spx.shopee.com.br/")
            await page.wait_for_selector('xpath=//*[@placeholder="Ops ID"]', timeout=10000)
            await page.locator('xpath=//*[@placeholder="Ops ID"]').fill('Ops134294')
            await page.locator('xpath=//*[@placeholder="Senha"]').fill('@Shopee123')
            await page.locator('xpath=/html/body/div[1]/div/div[2]/div/div/div[1]/div[3]/form/div/div/button').click()
            await page.wait_for_load_state("networkidle", timeout=40000)

            log("🧹 Limpando pop-ups...")
            await page.wait_for_timeout(5000)
            try: await page.keyboard.press("Escape")
            except: pass
            await page.evaluate('''() => {
                document.querySelectorAll('.ssc-dialog-wrapper, .ssc-dialog-mask').forEach(el => el.remove());
            }''')

            # Processa as duas bases
            for config in LISTA_DE_BASES:
                await processar_exportacao(page, config)

            log("🎉 TODOS OS PROCESSOS CONCLUÍDOS!")
            await page.wait_for_timeout(5000)

        except Exception as e:
            log(f"❌ Erro Geral: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
