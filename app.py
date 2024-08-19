from flask import Flask, request, jsonify
from flask_cors import CORS
from mongoengine import connect, Document, StringField, ListField, ReferenceField, DictField, DateField
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# Connect to MongoDB
connect(
    host=os.getenv("MONGO_URI")
)

# Define Models
class Roommate(Document):
    name = StringField(required=True)
    email = StringField(required=True)
    password = StringField(required=True)
    phone = StringField(required=True)

    def to_dict(self):
        return {"id": str(self.id), "name": self.name, "email": self.email, "phone": self.phone}

class Expense(Document):
    date = DateField(required=True)
    meal_type = StringField(required=True)
    items = ListField(DictField(), required=True)
    purchased_by = ReferenceField(Roommate, required=True)
    consumed_by = ListField(ReferenceField(Roommate), required=True)

    def to_dict(self):
        return {
            "id": str(self.id),
            "date": self.date.strftime('%Y-%m-%d'),
            "meal_type": self.meal_type,
            "items": self.items,
            "purchased_by": str(self.purchased_by.id) if self.purchased_by else None,
            "consumed_by": [str(roommate.id) for roommate in self.consumed_by]
        }

# Routes

@app.route('/add_roommate', methods=['POST', 'OPTIONS'])
def add_roommate():
    if request.method == 'OPTIONS':
        return '', 200
    
    data = request.json
    print(data)
    roommate = Roommate(name=data['uname'], email=data['uemail'], password=data['upass'], phone=data['uphone'])
    roommate.save()
    return jsonify({'message': 'Roommate added successfully'}), 201


@app.route('/login', methods=['POST', 'OPTIONS'])
def login():
    if request.method == 'OPTIONS':
        return '', 200

    data = request.json
    print(data)
    name = data.get('uname')
    password = data.get('upass')

    try:
        # Find the roommate by name and password
        roommate = Roommate.objects.get(name=name, password=password)
        # Return a success message with the user's name and ID
        return jsonify({
            "message": "Login successful",
            "name": roommate.name,
            "userId": str(roommate.id)  # Convert ObjectId to string
        }), 200
    except Roommate.DoesNotExist:
        return jsonify({"message": "Invalid name or password"}), 401

@app.route('/addExpense', methods=['POST', 'OPTIONS'])
def add_expense():
    if request.method == 'OPTIONS':
        # Handle preflight request here
        return '', 200

    if request.method == 'POST':
        try:
            data = request.json
            
            # Validate required fields
            required_fields = ['date', 'mealType', 'items', 'purchasedBy', 'consumedBy']
            missing_fields = [field for field in required_fields if field not in data or not data[field]]
            
            if missing_fields:
                return jsonify({"message": f"Missing or empty required fields: {', '.join(missing_fields)}"}), 400
            
            # Additional checks for specific fields
            if not isinstance(data['items'], list) or not all(isinstance(item, dict) for item in data['items']):
                return jsonify({"message": "Items must be a list of dictionaries"}), 400
            
            if not isinstance(data['consumedBy'], list) or not all(isinstance(id, str) for id in data['consumedBy']):
                return jsonify({"message": "ConsumedBy must be a list of roommate IDs"}), 400
            
            # Create and save the expense
            expense = Expense(
                date=datetime.strptime(data['date'], '%Y-%m-%d').date(),
                meal_type=data['mealType'],
                items=data['items'],
                purchased_by=Roommate.objects.get(id=data['purchasedBy']),
                consumed_by=[Roommate.objects.get(id=id) for id in data['consumedBy']]
            )
            expense.save()

            # Format the saved expense similarly to the get_expenses format
            total_cost = sum(item.get('cost', 0) for item in expense.items)
            expense_dict = expense.to_dict()

            # Add the purchased_by name
            purchased_by_name = expense.purchased_by.name if expense.purchased_by else None
            expense_dict['purchased_by_name'] = purchased_by_name

            # Add the consumed_by names
            consumed_by_names = [roommate.name for roommate in expense.consumed_by]
            expense_dict['consumed_by_names'] = consumed_by_names

            # Add the total cost
            expense_dict['total_cost'] = total_cost

            return jsonify(expense_dict), 201
        
        except Roommate.DoesNotExist:
            return jsonify({"message": "Roommate not found"}), 404
        except ValueError as ve:
            return jsonify({"message": f"Invalid data format: {str(ve)}"}), 400
        except Exception as e:
            print(f"Error: {e}")
            return jsonify({"message": "An error occurred while adding the expense"}), 500

@app.route('/roommates', methods=['GET'])
def get_roommates():
    roommates = Roommate.objects()
    return jsonify([roommate.to_dict() for roommate in roommates]), 200

@app.route('/expenses', methods=['GET'])
def get_expenses():
    expenses = Expense.objects()
    response = []

    for expense in expenses:
        total_cost = sum(item.get('cost', 0) for item in expense.items)
        expense_dict = expense.to_dict()
        
        # Add the purchased_by name
        purchased_by_name = expense.purchased_by.name if expense.purchased_by else None
        expense_dict['purchased_by_name'] = purchased_by_name
        
        # Add the consumed_by names
        consumed_by_names = [roommate.name for roommate in expense.consumed_by]
        expense_dict['consumed_by_names'] = consumed_by_names
        
        # Add the total cost
        expense_dict['total_cost'] = total_cost
        
        response.append(expense_dict)

    return jsonify(response), 200

@app.route('/split_expense', methods=['GET'])
def split_expense():
    start_date = datetime.strptime(request.args.get('start_date'), '%Y-%m-%d').date()
    start_of_week = start_date - timedelta(days=start_date.weekday())
    end_of_week = start_of_week + timedelta(days=6)
    
    expenses = Expense.objects(date__gte=start_of_week, date__lte=end_of_week)
    roommate_expenses = {str(roommate.id): {'name': roommate.name, 'amount': 0} for roommate in Roommate.objects()}
    
    for expense in expenses:
        total_cost = sum(item['cost'] for item in expense.items)
        split_amount = total_cost / len(expense.consumed_by)
        
        for roommate in expense.consumed_by:
            roommate_expenses[str(roommate.id)]['amount'] += split_amount
    
    return jsonify(roommate_expenses), 200

@app.route('/weekly_report', methods=['GET'])
def weekly_report():
    start_date = datetime.strptime(request.args.get('start_date'), '%Y-%m-%d').date()
    start_date = start_date - timedelta(days=start_date.weekday())
    end_date = start_date + timedelta(days=6)
    
    expenses = Expense.objects(date__gte=start_date, date__lte=end_date)
    
    report = {}
    spending = {}
    consumption = {}
    
    for expense in expenses:
        purchaser_id = str(expense.purchased_by.id)
        if purchaser_id not in spending:
            spending[purchaser_id] = 0
        spending[purchaser_id] += sum(item['cost'] for item in expense.items)
        
        for roommate in expense.consumed_by:
            roommate_id = str(roommate.id)
            if roommate_id not in report:
                report[roommate_id] = {
                    'name': roommate.name,
                    'total_amount': 0,
                    'total_items': 0,
                    'items': {},
                    'owed_by': [],
                    'owes_to': []
                }
            
            if roommate_id not in consumption:
                consumption[roommate_id] = 0
            consumption[roommate_id] += sum(item['cost'] for item in expense.items) / len(expense.consumed_by)
            
            for item in expense.items:
                if item['item'] not in report[roommate_id]['items']:
                    report[roommate_id]['items'][item['item']] = 0
                    report[roommate_id]['total_items'] += 1
                report[roommate_id]['items'][item['item']] += item['cost']
            
            report[roommate_id]['total_amount'] += sum(item['cost'] for item in expense.items)
    
    balances = {}
    for roommate_id, total_spent in spending.items():
        total_consumed = consumption.get(roommate_id, 0)
        balance = total_spent - total_consumed
        balances[roommate_id] = balance
        
    for roommate_id, balance in balances.items():
        if balance > 0:
            for other_id, other_balance in balances.items():
                if other_id != roommate_id and other_balance < 0:
                    amount = min(balance, -other_balance)
                    report[roommate_id]['owed_by'].append({
                        'user': report[other_id]['name'],
                        'amount': amount
                    })
                    report[other_id]['owes_to'].append({
                        'user': report[roommate_id]['name'],
                        'amount': amount
                    })
                    balances[roommate_id] -= amount
                    balances[other_id] += amount
                    if balances[roommate_id] == 0:
                        break
    
    report_list = []
    for roommate_id, data in report.items():
        report_list.append(data)
    
    return jsonify({
        'week_start_date': start_date.strftime('%Y-%m-%d'),
        'week_end_date': end_date.strftime('%Y-%m-%d'),
        'report': report_list
    }), 200

if __name__ == '__main__':
    app.run(debug=True, port=5001)
