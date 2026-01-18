import asyncio
from playwright.async_api import async_playwright
from datetime import datetime
import os
import shutil
import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials
import re

# ==============================
# Configuração de Ambiente
# ==============================
DOWNLOAD_DIR = "/tmp" 
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def rename_downloaded_file_handover(download_dir, download_path):
    try:
        current_hour = datetime.now().strftime("%H")
        new_file_name = f"PROD-{current_hour}.csv"
        new_file_path = os.path.join(download_dir, new_file_name)
        if os.path.exists(new_file_path): os.remove(new_file_path)
        shutil.move(download_path, new_file_path)
        print(f"✅ Arquivo salvo como: {new_file_name}")
        return new_file_path
    except Exception as e:
        print(f"❌ Erro ao renomear arquivo: {e}")
        return None

def update_google_sheets_handover(csv_file_path):
    try:
        if not os.path.exists(csv_file_path): return
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name("hxh.json", scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_url("https://docs.google.com/spreadsheets/d/1LZ8WUrgN36Hk39f7qDrsRwvvIy1tRXLVbl3-wSQn-Pc/edit#gid=734921183")
        worksheet = sheet.worksheet("Base Handedover")
        
        df = pd.read_csv(csv_file_path).fillna("")
        worksheet.clear()
        worksheet.update([df.columns.values.tolist()] + df.values.tolist())
        print("✅ Dados enviados para a aba 'Base Handedover'!")
    except Exception as e:
        print(f"❌ Erro no Google Sheets: {e}")

# ==============================
# Fluxo Principal com Cascata
# ==============================
async def main():
    async with async_playwright() as p:
        # Configuração idêntica ao script Pending para estabilidade
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            accept_downloads=True, 
            viewport={'width': 1366, 'height': 768}
        )
        page = await context.new_page()

        # Bloqueio de imagens para acelerar carregamento no GitHub
        await page.route("**/*.{png,jpg,jpeg,svg,gif}", lambda route: route.abort())

        try:
            # 1. LOGIN (Ops113074)
            print("🔐 Iniciando Login (Ops113074)...")
            await page.goto("https://spx.shopee.com.br/", wait_until="commit", timeout=120000)
            
            await page.locator('input[placeholder*="Ops ID"]').fill('Ops113074')
            await page.locator('input[placeholder*="Senha"]').fill('@Shopee123')
            await page.locator('button:has-text("Login"), button:has-text("Entrar"), .ant-btn-primary').first.click()
            
            print("⏳ Aguardando estabilização pós-login...")
            await page.wait_for_timeout(15000)
            await page.keyboard.press("Escape")

            # 2. NAVEGAÇÃO
            print("🚚 Acessando aba de Viagens...")
            await page.goto("https://spx.shopee.com.br/#/hubLinehaulTrips/trip", wait_until="domcontentloaded", timeout=90000)
            await page.wait_for_timeout(10000)

            # 3. ESTRATÉGIA DE CLIQUE EM CASCATA
            print("🔍 Iniciando tentativas de clique no filtro...")
            
            # Lista de tentativas baseada no XPath fornecido e seletores técnicos
            tentativas = [
                ("XPATH_FORNECIDO", "xpath=/html/body/div/div/div[2]/div[2]/div/div/div/div[2]/div[1]/div[1]/div/div[1]/div/div/div/div/div[3]/span"),
                ("CSS_POSICAO_TAB", ".ssc-tabs-tab:nth-child(2)"), # Segunda aba
                ("TEXTO_HANDEDOVER", "text='Handedover'"),
                ("TEXTO_EXPEDIDOS", "text='Expedidos'"),
                ("CSS_TAB_INDEX", "div[id*='tab-1']")
            ]

            clique_sucesso = False
            for nome, seletor in tentativas:
                try:
                    print(f"⏳ Testando método: {nome}...")
                    alvo = page.locator(seletor).first
                    
                    if await alvo.count() > 0:
                        # Evaluate click ignora se houver algo na frente do botão
                        await alvo.evaluate("el => el.click()")
                        print(f"✅ SUCESSO! O botão foi clicado usando o método: {nome}")
                        clique_sucesso = True
                        break
                except:
                    continue

            if not clique_sucesso:
                print("⚠️ Falha em todos os seletores. Tentando clique por posição fixa...")
                await page.mouse.click(200, 360) 

            await page.wait_for_timeout(10000)

            # 4. EXPORTAÇÃO
            print("📤 Clicando em Exportar...")
            await page.get_by_role("button", name="Exportar").first.evaluate("el => el.click()")
            await page.wait_for_timeout(12000)

            # 5. DOWNLOAD NO TASK CENTER
            print("📂 Navegando para o centro de tarefas...")
            await page.goto("https://spx.shopee.com.br/#/taskCenter/exportTaskCenter", wait_until="domcontentloaded")
            await page.wait_for_timeout(12000)

            # Garantir aba de download
            try:
                await page.get_by_text(re.compile(r"Exportar tarefa|Export Task", re.IGNORECASE)).first.click(timeout=5000)
            except: pass

            print("⬇️ Iniciando download...")
            async with page.expect_download(timeout=60000) as download_info:
                await page.locator("text=Baixar").first.evaluate("el => el.click()")

            download = await download_info.value
            path = os.path.join(DOWNLOAD_DIR, download.suggested_filename)
            await download.save_as(path)
            
            # Finalização
            final_path = rename_downloaded_file_handover(DOWNLOAD_DIR, path)
            if final_path:
                update_google_sheets_handover(final_path)
                print("\n🎉 PROCESSO HANDEDOVER CONCLUÍDO COM SUCESSO!")

        except Exception as e:
            print(f"❌ Erro crítico: {e}")
            # Tira print para conferirmos o que o robô está vendo se falhar
            try: await page.screenshot(path="debug_final.png")
            except: pass
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
