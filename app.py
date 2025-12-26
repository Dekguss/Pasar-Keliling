from flask import Flask, render_template, request, redirect, url_for, session, flash
import json
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'pasar_keliling_secret'

# --- HELPER FUNCTIONS ---
def load_data(filename):
    path = os.path.join('data', filename)
    if not os.path.exists(path): return []
    with open(path, 'r') as f: return json.load(f)

def save_data(filename, data):
    path = os.path.join('data', filename)
    with open(path, 'w') as f: json.dump(data, f, indent=4)

def get_next_id(data_list):
    if not data_list: return 1
    return max(item['id'] for item in data_list) + 1

# --- CORE ROUTES ---
@app.route('/')
def index():
    if 'user_id' in session:
        role = session.get('role')
        if role == 'pembeli': return redirect(url_for('buyer_home'))
        elif role == 'pedagang': return redirect(url_for('merchant_dashboard'))
        elif role == 'kurir': return redirect(url_for('courier_dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        users = load_data('users.json')
        user = next((u for u in users if u['username'] == username and u['password'] == password), None)
        if user:
            session['user_id'] = user['id']
            session['role'] = user['role']
            session['name'] = user['name']
            session['cart'] = []
            return redirect(url_for('index'))
        else:
            flash('Username atau password salah', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# --- BUYER ROUTES ---
@app.route('/home')
def buyer_home():
    if session.get('role') != 'pembeli': return redirect(url_for('login'))
    products = load_data('products.json')
    users = load_data('users.json')
    current_user = next((u for u in users if u['id'] == session['user_id']), {})
    return render_template('buyer_home.html', products=products, user=current_user)

@app.route('/product/<int:pid>')
def product_detail(pid):
    products = load_data('products.json')
    product = next((p for p in products if p['id'] == pid), None)
    return render_template('product_detail.html', product=product)

@app.route('/add_to_cart/<int:pid>', methods=['POST'])
def add_to_cart(pid):
    products = load_data('products.json')
    users = load_data('users.json')
    product = next((p for p in products if p['id'] == pid), None)
    
    if not product:
        return "Produk tidak ditemukan", 404
        
    qty = int(request.form.get('qty', 1))
    
    if 'cart' not in session:
        session['cart'] = []
    
    # Cek apakah item sudah ada di cart (dari toko yg sama/beda tidak masalah utk prototype)
    cart = session['cart']
    
    # Find merchant name from users data
    merchant = next((u for u in users if u['id'] == product['merchant_id'] and u['role'] == 'pedagang'), None)
    merchant_name = merchant['name'] if merchant else 'Toko'
    
    # Tambahkan item baru
    item = {
        'product_id': product['id'],
        'name': product['name'],
        'price': product['price'],
        'image': product['image'],
        'merchant_id': product['merchant_id'],
        'merchant_name': merchant_name,
        'qty': qty
    }
    cart.append(item)
    session['cart'] = cart
    return redirect(url_for('cart'))

@app.route('/cart')
def cart():
    cart_items = session.get('cart', [])
    total = sum(item['price'] * item['qty'] for item in cart_items)
    return render_template('cart.html', cart=cart_items, total=total)

@app.route('/checkout', methods=['POST'])
def checkout():
    cart = session.get('cart', [])
    if not cart: return redirect(url_for('buyer_home'))
    
    orders = load_data('orders.json')
    new_order_id = get_next_id(orders)
    
    # Untuk prototype, kita asumsikan 1 order 1 toko agar logic simple. 
    # Jika banyak toko, idealnya dipecah jadi sub-order.
    # Di sini kita ambil merchant_id dari item pertama saja untuk penyederhanaan.
    merchant_id = cart[0]['merchant_id'] if cart else 0
    
    new_order = {
        "id": new_order_id,
        "buyer_id": session['user_id'],
        "buyer_name": session['name'],
        "merchant_id": merchant_id,  # Penting untuk filter di dashboard pedagang
        "items": cart,
        "total_price": sum(item['price'] * item['qty'] for item in cart),
        "status": "Menunggu Konfirmasi", # Status Awal
        "date": datetime.now().strftime("%Y-%m-%d"),
        "courier_id": None
    }
    
    orders.append(new_order)
    save_data('orders.json', orders)
    session['cart'] = []
    return redirect(url_for('history'))

@app.route('/history')
def history():
    orders = load_data('orders.json')
    # Filter order milik pembeli ini
    my_orders = [o for o in orders if o['buyer_id'] == session['user_id']]
    # Sort descending (terbaru diatas)
    my_orders.sort(key=lambda x: x['id'], reverse=True)
    return render_template('history.html', orders=my_orders)

# --- MERCHANT ROUTES (CRUD & ACC) ---
@app.route('/merchant')
def merchant_dashboard():
    if session.get('role') != 'pedagang': 
        return redirect(url_for('login'))
    
    products = load_data('products.json')
    orders = load_data('orders.json')
    users = load_data('users.json')
    
    # Filter produk milik pedagang ini
    my_products = [p for p in products if p['merchant_id'] == session['user_id']]
    
    # Process orders to ensure all items have required fields
    for order in orders:
        if 'items' in order and isinstance(order['items'], list):
            for item in order['items']:
                # Ensure each item has merchant_name
                if 'merchant_name' not in item and 'merchant_id' in item:
                    merchant = next((u for u in users if u['id'] == item['merchant_id'] and u['role'] == 'pedagang'), None)
                    if merchant:
                        item['merchant_name'] = merchant.get('name', 'Toko')
    
    # Filter orderan masuk untuk pedagang ini
    incoming_orders = [o for o in orders if o.get('merchant_id') == session['user_id']]
    incoming_orders.sort(key=lambda x: x['id'], reverse=True)

    return render_template('merchant.html', products=my_products, orders=incoming_orders)

@app.route('/merchant/product/add', methods=['GET', 'POST'])
def merchant_add_product():
    if session.get('role') != 'pedagang': return redirect(url_for('login'))
    
    if request.method == 'POST':
        products = load_data('products.json')
        new_product = {
            "id": get_next_id(products),
            "merchant_id": session['user_id'],
            "merchant_name": session['name'],
            "name": request.form['name'],
            "price": int(request.form['price']),
            "image": request.form['image'], # URL Gambar
            "rating": 0.0,
            "desc": request.form['desc'],
            "stock": int(request.form['stock'])
        }
        products.append(new_product)
        save_data('products.json', products)
        return redirect(url_for('merchant_dashboard'))
        
    return render_template('merchant_form.html', mode='add')

@app.route('/merchant/product/edit/<int:pid>', methods=['GET', 'POST'])
def merchant_edit_product(pid):
    if session.get('role') != 'pedagang': return redirect(url_for('login'))
    
    products = load_data('products.json')
    product = next((p for p in products if p['id'] == pid and p['merchant_id'] == session['user_id']), None)
    
    if not product: return redirect(url_for('merchant_dashboard'))

    if request.method == 'POST':
        product['name'] = request.form['name']
        product['price'] = int(request.form['price'])
        product['image'] = request.form['image']
        product['desc'] = request.form['desc']
        product['stock'] = int(request.form['stock'])
        save_data('products.json', products)
        return redirect(url_for('merchant_dashboard'))

    return render_template('merchant_form.html', mode='edit', product=product)

@app.route('/merchant/product/delete/<int:pid>')
def merchant_delete_product(pid):
    if session.get('role') != 'pedagang': return redirect(url_for('login'))
    
    products = load_data('products.json')
    # Filter list untuk menghilangkan produk yg dihapus
    products = [p for p in products if not (p['id'] == pid and p['merchant_id'] == session['user_id'])]
    save_data('products.json', products)
    return redirect(url_for('merchant_dashboard'))

@app.route('/merchant/order/accept/<int:oid>')
def merchant_accept_order(oid):
    if session.get('role') != 'pedagang': return redirect(url_for('login'))
    
    orders = load_data('orders.json')
    for o in orders:
        if o['id'] == oid and o['merchant_id'] == session['user_id']:
            o['status'] = 'Siap Diantar' # Ubah status agar muncul di kurir
    save_data('orders.json', orders)
    return redirect(url_for('merchant_dashboard'))

# --- COURIER ROUTES ---
@app.route('/courier')
def courier_dashboard():
    if session.get('role') != 'kurir': return redirect(url_for('login'))
    orders = load_data('orders.json')
    
    # Kurir hanya melihat order yang SUDAH di-ACC pedagang ("Siap Diantar")
    # ATAU order yang sedang dia bawa sendiri ("Sedang Diantar")
    available_orders = []
    for o in orders:
        if o['status'] == 'Siap Diantar':
            available_orders.append(o)
        elif o['status'] == 'Sedang Diantar' and o['courier_id'] == session['user_id']:
            available_orders.append(o)
            
    return render_template('courier.html', orders=available_orders)

@app.route('/courier/take/<int:oid>')
def courier_take_order(oid):
    if session.get('role') != 'kurir': return redirect(url_for('login'))
    
    orders = load_data('orders.json')
    for o in orders:
        # Pastikan status masih Siap Diantar (belum diambil kurir lain)
        if o['id'] == oid and o['status'] == 'Siap Diantar':
            o['status'] = 'Sedang Diantar'
            o['courier_id'] = session['user_id']
    save_data('orders.json', orders)
    return redirect(url_for('courier_dashboard'))

@app.route('/courier/map/<int:oid>')
def courier_map(oid):
    if session.get('role') != 'kurir': return redirect(url_for('login'))
    
    orders = load_data('orders.json')
    order = next((o for o in orders if o['id'] == oid), None)
    
    if not order:
        return redirect(url_for('courier_dashboard'))
        
    return render_template('courier_map.html', order=order)

@app.route('/courier/finish/<int:oid>')
def courier_finish_order(oid):
    if session.get('role') != 'kurir': return redirect(url_for('login'))
    
    orders = load_data('orders.json')
    for o in orders:
        if o['id'] == oid and o['courier_id'] == session['user_id']:
            o['status'] = 'Selesai'
    save_data('orders.json', orders)
    return redirect(url_for('courier_dashboard'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)