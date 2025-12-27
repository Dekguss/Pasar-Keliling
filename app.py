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
        elif role == 'pedagang': return redirect(url_for('merchant_orders'))
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
            if 'address' in user:
                session['address'] = user['address']
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

@app.route('/all-products')
def all_products():
    if session.get('role') != 'pembeli': return redirect(url_for('login'))
    
    products = load_data('products.json')
    
    # (Opsional) Fitur Search sederhana via URL parameter ?q=apel
    query = request.args.get('q')
    if query:
        products = [p for p in products if query.lower() in p['name'].lower()]
        
    return render_template('all_products.html', products=products)

@app.route('/product/<int:pid>')
def product_detail(pid):
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    products = load_data('products.json')
    users = load_data('users.json')
    
    product = next((p for p in products if p['id'] == pid), None)
    if not product:
        return "Produk tidak ditemukan", 404
        
    merchant = next((u for u in users if u['id'] == product['merchant_id']), {})
    
    return render_template(
        'product_detail.html', 
        product=product, 
        merchant=merchant
    )

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
    return redirect(url_for('product_detail', pid=pid))

@app.route('/remove_from_cart/<int:index>', methods=['POST'])
def remove_from_cart(index):
    if 'cart' not in session:
        return redirect(url_for('cart'))
        
    cart = session.get('cart', [])
    
    if 0 <= index < len(cart):
        cart.pop(index)
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
    
    payment_method = request.form.get('payment_method', 'cod')  # Default to 'cod' if not provided
    
    # Map payment method codes to display names
    payment_methods = {
        'saldo': 'Saldo',
        'cod': 'Bayar di Tempat (COD)',
        'transfer': 'Transfer Bank',
        'e-wallet': 'E-Wallet'
    }
    
    payment_display = payment_methods.get(payment_method, 'Bayar di Tempat (COD)')
    
    orders = load_data('orders.json')
    new_order_id = get_next_id(orders)
    
    # Untuk prototype, kita asumsikan 1 order 1 toko agar logic simple. 
    # Jika banyak toko, idealnya dipecah jadi sub-order.
    # Di sini kita ambil merchant_id dari item pertama saja untuk penyederhanaan.
    merchant_id = cart[0]['merchant_id'] if cart else 0
    
    # Get user data to ensure we have the latest address
    users = load_data('users.json')
    current_user = next((u for u in users if u['id'] == session.get('user_id')), {})
    
    new_order = {
        "id": new_order_id,
        "buyer_id": session.get('user_id'),
        "buyer_name": session.get('name', 'Pembeli'),
        "buyer_address": current_user.get('address', 'Alamat belum diatur'),
        "merchant_id": merchant_id,  # Penting untuk filter di dashboard pedagang
        "items": cart,
        "total_price": sum(item['price'] * item['qty'] for item in cart),
        "payment_method": payment_display,
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
    if 'user_id' not in session or session.get('role') != 'pembeli':
        return redirect(url_for('login'))
    
    orders = load_data('orders.json')
    # Filter pesanan milik user yang sedang login
    my_orders = []
    for order in orders:
        if order.get('buyer_id') == session['user_id']:
            # Buat salinan order untuk menghindari perubahan pada data asli
            order_copy = order.copy()
            
            # Gunakan 'order_items' sebagai ganti 'items' untuk menghindari konflik dengan method dict.items()
            if 'items' in order_copy and isinstance(order_copy['items'], list) and not hasattr(order_copy['items'], '__call__'):
                order_items = order_copy['items']
            else:
                order_items = []
            
            # Pastikan setiap item memiliki semua field yang diperlukan
            processed_items = []
            for item in order_items:
                if not isinstance(item, dict):
                    continue
                processed_item = item.copy()
                processed_item.setdefault('image', '')
                processed_item.setdefault('name', 'Produk tidak tersedia')
                processed_item.setdefault('price', 0)
                processed_item.setdefault('qty', 1)
                processed_items.append(processed_item)
            
            # Update order_copy dengan items yang sudah diproses
            order_copy['order_items'] = processed_items
            my_orders.append(order_copy)
    
    # Urutkan dari yang terbaru (ID terbesar diatas)
    my_orders.sort(key=lambda x: x.get('id', 0), reverse=True)
    
    return render_template('history.html', orders=my_orders)

@app.route('/track-order/<int:order_id>')
def track_order(order_id):
    if 'user_id' not in session or session.get('role') != 'pembeli':
        return redirect(url_for('login'))
    
    orders = load_data('orders.json')
    order = next((o for o in orders if o['id'] == order_id and o['buyer_id'] == session['user_id']), None)
    
    if not order:
        flash('Pesanan tidak ditemukan', 'error')
        return redirect(url_for('history'))
    
    return render_template('track_order.html', order=order)

# --- MERCHANT ROUTE ---

# 1. Halaman Utama (Pesanan Masuk)
@app.route('/merchant')
@app.route('/merchant/orders')
def merchant_orders():
    if session.get('role') != 'pedagang': return redirect(url_for('login'))
    
    orders = load_data('orders.json')
    # Filter orderan masuk untuk pedagang ini
    incoming_orders = [o for o in orders if o.get('merchant_id') == session['user_id']]
    incoming_orders.sort(key=lambda x: x['id'], reverse=True)

    return render_template('merchant_orders.html', orders=incoming_orders, page='orders')

# 2. Halaman Kelola Produk
@app.route('/merchant/products')
def merchant_products():
    if session.get('role') != 'pedagang': return redirect(url_for('login'))
    
    products = load_data('products.json')
    # Filter produk milik pedagang ini
    my_products = [p for p in products if p['merchant_id'] == session['user_id']]
    
    return render_template('merchant_products.html', products=my_products, page='products')

# 3. Halaman Tambah Produk (Sudah ada, tidak perlu diubah logicnya)
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
            "image": request.form['image'],
            "rating": 0.0,
            "desc": request.form['desc'],
            "stock": int(request.form['stock'])
        }
        products.append(new_product)
        save_data('products.json', products)
        # Setelah tambah, kembali ke halaman produk
        return redirect(url_for('merchant_products')) 
        
    return render_template('merchant_form.html', mode='add')

@app.route('/merchant/products/<int:pid>/edit', methods=['GET', 'POST'])
def merchant_edit_product(pid):
    if session.get('role') != 'pedagang':
        return redirect(url_for('login'))
    
    products = load_data('products.json')
    product = next((p for p in products if p['id'] == pid), None)
    
    if not product or product['merchant_id'] != session['user_id']:
        flash('Produk tidak ditemukan', 'error')
        return redirect(url_for('merchant_products'))
    
    if request.method == 'POST':
        # Update product details
        product['name'] = request.form['name']
        product['price'] = int(request.form['price'])
        product['stock'] = int(request.form['stock'])
        product['image'] = request.form['image']
        
        save_data('products.json', products)
        flash('Produk berhasil diperbarui', 'success')
        return redirect(url_for('merchant_products'))
    
    return render_template('merchant_form.html', mode='edit', product=product)

@app.route('/merchant/products/<int:pid>/delete', methods=['POST'])
def merchant_delete_product(pid):
    if session.get('role') != 'pedagang':
        return redirect(url_for('login'))
    
    products = load_data('products.json')
    product = next((p for p in products if p['id'] == pid), None)
    
    if product and product['merchant_id'] == session['user_id']:
        products = [p for p in products if p['id'] != pid]
        save_data('products.json', products)
        flash('Produk berhasil dihapus', 'success')
    else:
        flash('Produk tidak ditemukan', 'error')
    
    return redirect(url_for('merchant_products'))

@app.route('/merchant/orders/<int:oid>/accept', methods=['GET', 'POST'])
def merchant_accept_order(oid):
    if session.get('role') != 'pedagang': 
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        orders = load_data('orders.json')
        order = next((o for o in orders if o['id'] == oid), None)
        
        if not order:
            flash('Pesanan tidak ditemukan', 'error')
            return redirect(url_for('merchant_orders'))
            
        if order['merchant_id'] != session['user_id']:
            flash('Anda tidak memiliki akses ke pesanan ini', 'error')
            return redirect(url_for('merchant_orders'))
        
        # Update status pesanan
        order['status'] = 'Menunggu Kurir'
        save_data('orders.json', orders)
        
        flash('Pesanan berhasil diterima', 'success')
    
    return redirect(url_for('merchant_orders'))

# --- COURIER ROUTES ---
@app.route('/courier')
def courier_dashboard():
    if session.get('role') != 'kurir': 
        return redirect(url_for('login'))
    
    orders = load_data('orders.json')
    tab = request.args.get('tab', 'available')  # Default to 'available' tab
    
    available_orders = []
    history_orders = []
    
    for o in orders:
        # Orders that are waiting to be picked up or being delivered by this courier
        if o['status'] in ['Menunggu Kurir', 'Siap Diantar']:
            available_orders.append(o)
        elif o['status'] in ['Sedang Diantar', 'Selesai'] and o.get('courier_id') == session['user_id']:
            if o['status'] == 'Selesai':
                history_orders.append(o)
            else:
                available_orders.append(o)
    
    # Sort history by date (newest first)
    history_orders.sort(key=lambda x: x.get('date', ''), reverse=True)
    
    return render_template('courier.html', 
                         orders=available_orders if tab == 'available' else history_orders,
                         current_tab=tab)

@app.route('/courier/take/<int:oid>')
def courier_take_order(oid):
    if session.get('role') != 'kurir': return redirect(url_for('login'))
    
    orders = load_data('orders.json')
    for o in orders:
        # Pastikan status masih Siap Diantar (belum diambil kurir lain)
        if o['id'] == oid and o['status'] == 'Menunggu Kurir':
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
    app.run(host='0.0.0.0', port=port, debug=True)
