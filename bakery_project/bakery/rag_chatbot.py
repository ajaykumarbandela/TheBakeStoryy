"""
RAG Chatbot for Django SQLite Database
Extracts data from 5 models: MenuItem, Order, OrderItem, Payment, UserProfile
"""

import os
import django
from dotenv import load_dotenv
from django.contrib.auth.models import User

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bakery_project.settings')
django.setup()

# RAG imports
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_groq import ChatGroq

# Django models
from bakery.models import MenuItem, Order, OrderItem, Payment, UserProfile
from django.contrib.auth.models import User

# Load environment variables
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")


# ==================================================
# CUSTOM ADDITIONAL INFORMATION
# ==================================================
# Add any additional information about your bakery here
# This data will be included in the chatbot's knowledge base
# You can type manually whatever information you want the chatbot to know

ADDITIONAL_BAKERY_INFO = """

=== ADDITIONAL BAKERY INFORMATION ===

Store Hours:
Monday to Friday: 8:00 AM - 8:00 PM
Saturday to Sunday: 9:00 AM - 9:00 PM
Holidays: 10:00 AM - 6:00 PM

Contact Information:
Phone: +91 8074691873
Email: bandelaajay360@gmail.com
Address: 123 Qspiders, Dilsuknagar, Hyderabad, Telangana, India

Special Services:
- Custom cake orders (minimum 2 days advance notice)
- Birthday party catering available
- Wedding cake consultations by appointment
- Gluten-free options available on request
- Vegan desserts available

Delivery Information:
- Free delivery for orders above ₹500
- Delivery available within 10km radius
- Same-day delivery for orders placed before 12 PM

Payment Methods Accepted:
- Cash on Delivery
- UPI (Google Pay, PhonePe, Paytm)
- Credit/Debit Cards
- Net Banking

Special Offers:
- 10% discount on orders above ₹1000
- Buy 5 cupcakes, get 1 free
- Birthday month special: 15% off on custom cakes

About Us:
The Bake Story is a premium bakery specializing in artisanal breads, 
custom cakes, and delicious pastries. We use only the finest ingredients 
and traditional baking methods to create memorable treats for every occasion.

Our Specialties:
- Custom Designer Cakes
- French Macarons
- Artisan Sourdough Bread
- Handcrafted Chocolates
- Fresh Croissants Daily


developer: This chatbot was built by Ajay, a Python developer trainer by monty sir and deva sir.
who is deva: Deva is a senior Python developer and mentor who has been guiding Ajay and ajays django trainer who was expertise in django programming and also in data analysis.
who is monty sir: Monty sir is a lead trainer at Qspiders who has trained Ajay in Python development.
about qspiders: Qspiders is a leading software training institute in India, specializing in quality software testing and development courses.
famous bakery in hyderabad: The Bake Story is one of the most famous bakeries in Hyderabad, known for its delicious cakes and pastries.

about Ajay: Ajay is a passionate Python developer. He enjoys building practical applications and sharing his knowledge with aspiring developers.
Ajay's Interests: Coding, Teaching, Baking, Traveling,Gym.
Ajay is trained at Qspiders institute by monty sir & deva sir & shubam sir and rahul sir.
Ajay completed his B.Tech in Electronics and communication Engineering  from MVSR engineering college.

shubam sir is a senior web developer and mentor who has been guiding Ajay in his web development journey.
monty sir is a lead python trainer at Qspiders who has trained Ajay in Python development.
rahul sir is a senior web developer and mentor who has been guiding Ajay in react js and frontend development.
=== END OF ADDITIONAL INFORMATION ===

"""
# ==================================================


# ---------------------------
# 1) LOAD DATA FROM DATABASE
# ---------------------------
def load_database_data():
    """
    Extracts data from all 5 Django models and formats them as text documents
    """
    documents = []
    
    # 1. MenuItem data
    print("📦 Loading MenuItem data...")
    menu_items = MenuItem.objects.all()
    for item in menu_items:
        doc = f"""
Menu Item: {item.name}
Category: {item.get_category_display()}
Price: ₹{item.price}
Description: {item.description}
Available: {'Yes' if item.available else 'No'}
Created: {item.created_at.strftime('%Y-%m-%d')}
"""
        documents.append(doc)
    
    # 2. Order data
    print("📦 Loading Order data...")
    orders = Order.objects.all()
    for order in orders:
        items_list = ", ".join([f"{item.quantity}x {item.menu_item.name}" 
                                for item in order.items.all()])
        doc = f"""
Order ID: {order.order_id}
Customer: {order.user.username}
Status: {order.get_status_display()}
Total Amount: ₹{order.total_amount}
Delivery Fee: ₹{order.delivery_fee}
Grand Total: ₹{order.grand_total}
Items: {items_list}
Delivery Address: {order.delivery_address}
Delivery Phone: {order.delivery_phone}
Created: {order.created_at.strftime('%Y-%m-%d %H:%M')}
"""
        documents.append(doc)
    
    # 3. OrderItem data
    print("📦 Loading OrderItem data...")
    order_items = OrderItem.objects.select_related('order', 'menu_item').all()
    for item in order_items:
        doc = f"""
Order Item: {item.menu_item.name}
Order ID: {item.order.order_id}
Quantity: {item.quantity}
Price per Unit: ₹{item.price}
Subtotal: ₹{item.subtotal}
Customer: {item.order.user.username}
"""
        documents.append(doc)
    
    # 4. Payment data
    print("📦 Loading Payment data...")
    payments = Payment.objects.select_related('order').all()
    for payment in payments:
        doc = f"""
Payment Transaction: {payment.transaction_id}
Order ID: {payment.order.order_id}
Payment Method: {payment.get_payment_method_display()}
Payment Status: {payment.get_payment_status_display()}
Amount: ₹{payment.amount}
UPI ID: {payment.upi_id if payment.upi_id else 'N/A'}
Created: {payment.created_at.strftime('%Y-%m-%d %H:%M')}
Paid At: {payment.paid_at.strftime('%Y-%m-%d %H:%M') if payment.paid_at else 'Not paid'}
"""
        documents.append(doc)
    
    # 5. UserProfile data
    print("📦 Loading UserProfile data...")
    profiles = UserProfile.objects.select_related('user').all()
    for profile in profiles:
        doc = f"""
User Profile: {profile.user.username}
Email: {profile.user.email}
Phone: {profile.phone}
Address: {profile.address}
City: {profile.city}
State: {profile.state}
Pincode: {profile.pincode}
Member Since: {profile.created_at.strftime('%Y-%m-%d')}
"""
        documents.append(doc)




  # 6. User data (basic auth info only)
    print("📦 Loading User data...")
    users = User.objects.all()
    for user in users:
        doc = f"""
User: {user.username}
Email: {user.email}
First Name: {user.first_name}
Last Name: {user.last_name}
Active: {'Yes' if user.is_active else 'No'}
Staff: {'Yes' if user.is_staff else 'No'}
Member Since: {user.date_joined.strftime('%Y-%m-%d')}
"""
        documents.append(doc)
    
    # 7. Add custom additional information
    print("📦 Loading Additional Bakery Information...")
    documents.append(ADDITIONAL_BAKERY_INFO)
    
    print(f"✅ Loaded {len(documents)} documents from database")
    return documents
# ---------------------------
# 2) CHUNK TEXT
# ---------------------------
def split_text(documents):
    """Split documents into smaller chunks for better retrieval"""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=100
    )
    all_text = "\n\n---\n\n".join(documents)
    return splitter.split_text(all_text)


# ---------------------------
# 3) CREATE VECTOR STORE
# ---------------------------
def create_vectorstore(chunks):
    """Create FAISS vector store from text chunks"""
    try:
        print(f"   Creating embeddings model...")
        embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
        print(f"   Creating vector store from {len(chunks)} chunks...")
        vectorstore = FAISS.from_texts(chunks, embeddings)
        print(f"   ✅ Vector store created successfully!")
        return vectorstore
    except Exception as e:
        print(f"   ❌ Error creating vector store: {e}")
        import traceback
        traceback.print_exc()
        raise


# ---------------------------
# 4) ASK GROQ + RAG
# ---------------------------
def answer_question(query, vectorstore, llm):
    """
    Answer questions using RAG (Retrieval Augmented Generation)
    """
    # Retrieve relevant documents
    docs = vectorstore.similarity_search(query, k=5)
    context = "\n\n".join([doc.page_content for doc in docs])

    prompt = f"""You are a helpful and knowledgeable chatbot assistant for The Bake Story bakery.
Use the following context from the bakery database to answer user questions.
    every time if user is logined in say hello {  User.first_name } or hello { User.username } instead of hello nikhil or rahul or some other random names from database always say buddy or hello dear .
you are the bake story's personal assistant. Provide accurate and concise information based on the database content.
try to answer based on the database content provided. If the answer is not found, respond with "I don't have that information."
behave professionally and courteously as a customer service assistant. always aim to help the user with their queries.
tell customers about bakery products, orders, payments, and user profiles based on the database.
if customers ask for recommendations, suggest popular bakery items from the menu.
if the question is unrelated to the bakery database, politely inform the user that you can only assist with bakery-related queries.
if the user asks for multiple pieces of information, provide a structured response covering all points.
give examples of menu items, order statuses, payment methods, and user profile details when relevant.
give priority to recent data (e.g., latest orders, recent payments) when answering time-sensitive questions.
if the user asks for statistics (e.g., number of orders, total sales), provide accurate counts based on the database context.
if the user requests help with placing an order or making a payment, guide them through the process based on the database information.
if the user inquires about specific menu items, provide detailed descriptions including price and availability.
check for any inconsistencies in the database context and clarify them if needed.
tell the exact address and contact details for delivery based on the order information.
the order will be delivered within 30-45 minutes of placing the order.
pure native ingredients are used in all bakery products.
no charges for delivery within the city limits.
no chemicals or preservatives are used in any bakery items.
no hidden charges. the price mentioned is the final price.

all are freshly baked items.
give importance to customer satisfaction and quality service.
give answer in a friendly and engaging manner.
be friendly and polite in your responses and ask to visit again.
tell the user to visit the bakery for more delicious items.

every time mention the chartbot was built by Ajay a python developer.

and when i ask something you are saying  hello nikhil hello rahul or some other names  dont take some random names from database instead always say buddy or hello dear .
The database contains information about:
- Menu items (bakery products, prices, availability)
- Orders (customer orders, status, delivery details)
- Order items (items within each order)
- Payments (transaction details, payment methods)
- User profiles (customer information)

CONTEXT FROM DATABASE:
{context}

QUESTION: {query}

ANSWER (provide clear, helpful information based  on the database context and ADDITIONAL_BAKERY_INFO if question is about ajay. deva, monty, shubam, rahul, qspiders or about bakery or about chatbot developer give entire data about them):
"""

    response = llm.invoke(prompt)
    return response.content


# ---------------------------
# 5) INITIALIZE CHATBOT
# ---------------------------
class DatabaseRAGChatbot:
    """Main chatbot class for database RAG"""
    
    def __init__(self, groq_api_key):
        self.llm = ChatGroq(
            groq_api_key=groq_api_key,
            model="llama-3.1-8b-instant"
        )
        self.vectorstore = None
        
    def initialize(self):
        """Load database and create vector store"""
        print("\n🚀 Initializing Database RAG Chatbot...")
        
        # Load data from database
        documents = load_database_data()
        
        # Split into chunks
        print("✂ Splitting documents into chunks...")
        chunks = split_text(documents)
        
        # Build vectorstore
        print("🧠 Creating vector store...")
        self.vectorstore = create_vectorstore(chunks)
        
        print("\n🎉 Chatbot Initialized! Ready to answer questions.\n")
        
    def ask(self, query):
        """Ask a question and get an answer"""
        if not self.vectorstore:
            return "Error: Chatbot not initialized. Call initialize() first."
        
        return answer_question(query, self.vectorstore, self.llm)
    
    def refresh_data(self):
        """Refresh the vector store with latest database data"""
        print("\n🔄 Refreshing database data...")
        self.initialize()


# ---------------------------------------------------
# MAIN APP (for testing)
# ---------------------------------------------------
if __name__ == "__main__":
    # Initialize chatbot
    chatbot = DatabaseRAGChatbot(GROQ_API_KEY)
    chatbot.initialize()

    print("\n" + "="*50)
    print("🤖 BAKERY DATABASE CHATBOT")
    print("="*50)
    print("\nExample questions you can ask:")
    print("- What menu items do you have?")
    print("- Show me all cake items")
    print("- What is the status of order ORD123?")
    print("- List all pending orders")
    print("- What payment methods are available?")
    print("- Show customer information")
    print("- Type 'refresh' to reload database data")
    print("- Type 'exit' to quit\n")

    # Chat Loop
    while True:
        query = input("🔎 Ask a question: ")

        if query.lower() == "exit":
            print("👋 Exiting...")
            break
        
        if query.lower() == "refresh":
            chatbot.refresh_data()
            continue

        # Answer using Groq RAG
        print("\n🤖 Thinking...")
        answer = chatbot.ask(query)
        print("\n📝 Answer:", answer, "\n")
