from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

# Initialize the Flask application
app = Flask(__name__)

# Configure the database connection
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///hospital.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your_super_secret_key_here_HMA' # Essential for sessions and flash messages

# Initialize the SQLAlchemy extension
db = SQLAlchemy(app)

# This makes the datetime object available in all Jinja templates
@app.context_processor
def inject_datetime():
    return {'datetime': datetime}
# ---------------------------------------------------------

# ----------------- Models -----------------

class Department(db.Model):
    __tablename__ = 'departments'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False)
    description = db.Column(db.Text)
    
    doctors = db.relationship('User', backref='specialization', lazy='dynamic', foreign_keys='User.specialization_id')
    appointments = db.relationship('Appointment', backref='department_rel', lazy='dynamic') 

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    specialization_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=True)
    
    # New Fields for better management
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    date_of_birth = db.Column(db.Date, nullable=True)

    username = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(150), nullable=False) # Store hash, not raw password
    role = db.Column(db.String(150), nullable=False) # admin, doctor, patient
    created_at = db.Column(db.DateTime, default=datetime.utcnow) 

    # Helper function to set password
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    # Helper function to check password
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    # Appointments relationship (patient/user side)
    patient_appointments = db.relationship('Appointment', backref='patient', lazy='dynamic', foreign_keys='Appointment.patient_id')
    # Appointments relationship (doctor side - assuming only doctors are assigned appointments)
    doctor_appointments = db.relationship('Appointment', backref='doctor', lazy='dynamic', foreign_keys='Appointment.doctor_id')


class Treatment(db.Model):
    __tablename__ = 'treatments'
    id = db.Column(db.Integer, primary_key=True)
    treatment_name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text)
    
    appointments = db.relationship('Appointment', backref='treatment', lazy='dynamic')


class Appointment(db.Model):
    __tablename__ = 'appointments'
    id = db.Column(db.Integer, primary_key=True)
    appointment_datetime = db.Column(db.DateTime, nullable=False) 
    status = db.Column(db.String(21), default='Booked') # Status: Booked, Completed, Cancelled
    
    # Foreign Keys
    patient_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False) # The person requesting the appointment
    doctor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True) # The assigned doctor (can be null initially)
    treatment_id = db.Column(db.Integer, db.ForeignKey('treatments.id'), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=False) # Department needed for booking logic

# ----------------- Routes -----------------

def is_logged_in():
    return 'user_id' in session

@app.route('/')
def home():
    if is_logged_in():
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if is_logged_in():
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            session['logged_in'] = True
            session['user_id'] = user.id
            session['role'] = user.role
            flash(f'Welcome back, {user.first_name}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password.', 'danger')
            return render_template('login.html')

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            # For simplicity, we only allow patient registration through this form
            new_user = User(
                first_name = request.form['first_name'],
                last_name = request.form['last_name'],
                username = request.form['username'],
                email = request.form['email'],
                role = 'patient'
            )
            new_user.set_password(request.form['password'])
            
            db.session.add(new_user)
            db.session.commit()
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error during registration: {e}', 'danger')

    return render_template('register.html')


@app.route('/dashboard')
def dashboard():
    if not is_logged_in():
        flash('Please log in to view the dashboard.', 'warning')
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    user = User.query.get(user_id)
    
    if user.role == 'admin':
        # Admin dashboard logic: count users, appointments, etc.
        user_count = User.query.count()
        appointment_count = Appointment.query.count()
        dept_count = Department.query.count()
        context = {
            'user': user,
            'user_count': user_count,
            'appointment_count': appointment_count,
            'dept_count': dept_count,
            'recent_appointments': Appointment.query.order_by(Appointment.appointment_datetime.desc()).limit(5).all()
        }
    elif user.role == 'doctor':
        # Doctor dashboard logic: view assigned appointments
        appointments = Appointment.query.filter_by(doctor_id=user_id).order_by(Appointment.appointment_datetime.asc()).all()
        context = {
            'user': user,
            'appointments': appointments
        }
    elif user.role == 'patient':
        # Patient dashboard logic: view their own appointments
        appointments = Appointment.query.filter_by(patient_id=user_id).order_by(Appointment.appointment_datetime.asc()).all()
        departments = Department.query.all()
        treatments = Treatment.query.all()
        context = {
            'user': user,
            'appointments': appointments,
            'departments': departments,
            'treatments': treatments
        }
    else:
        context = {'user': user}

    return render_template('dashboard.html', **context)


# Example Admin Route: Manage Departments (CRUD)
@app.route('/admin/departments', methods=['GET', 'POST'])
def manage_departments():
    if not is_logged_in() or session.get('role') != 'admin':
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        try:
            name = request.form['name']
            description = request.form['description']
            new_dept = Department(name=name, description=description)
            db.session.add(new_dept)
            db.session.commit()
            flash(f'Department "{name}" added successfully.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding department: {e}', 'danger')
        return redirect(url_for('manage_departments'))

    departments = Department.query.all()
    return render_template('admin_departments.html', departments=departments)

# Placeholder route for appointment booking
@app.route('/book_appointment', methods=['POST'])
def book_appointment():
    if not is_logged_in() or session.get('role') != 'patient':
        flash('You must be logged in as a patient to book an appointment.', 'danger')
        return redirect(url_for('login'))
    
    try:
        # Note: You would need a proper form/UI for this, but this is a backend placeholder
        dept_id = request.form['department_id']
        treatment_id = request.form['treatment_id']
        # Simple datetime parsing (You should use a proper date/time picker in the UI)
        app_dt_str = request.form['appointment_datetime']
        app_dt = datetime.strptime(app_dt_str, '%Y-%m-%dT%H:%M') # Format from datetime-local input
        
        # Simple auto-assignment of doctor (This needs proper scheduling logic in a real app)
        available_doctor = User.query.filter_by(role='doctor', specialization_id=dept_id).first()
        
        new_appointment = Appointment(
            patient_id=session['user_id'],
            doctor_id=available_doctor.id if available_doctor else None, # Assign if doctor exists
            treatment_id=treatment_id,
            department_id=dept_id,
            appointment_datetime=app_dt,
            status='Booked'
        )
        
        db.session.add(new_appointment)
        db.session.commit()
        flash('Appointment booked successfully! A doctor will be assigned shortly.', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Failed to book appointment. Error: {e}', 'danger')
        
    return redirect(url_for('dashboard'))

# ----------------- DB Initialization -----------------

# Utility function to initialize and populate the database with seed data
def seed_data():
    if not Department.query.first():
        db.session.add(Department(name="Cardiology", description="Heart-related issues."))
        db.session.add(Department(name="Neurology", description="Nervous system disorders."))
        db.session.add(Department(name="Orthopaedics", description="Musculoskeletal system."))
        db.session.commit()

    if not Treatment.query.first():
        db.session.add(Treatment(treatment_name="Consultation", description="General check-up."))
        db.session.add(Treatment(treatment_name="EKG", description="Electrocardiogram."))
        db.session.add(Treatment(treatment_name="MRI Scan", description="Magnetic Resonance Imaging."))
        db.session.add(Treatment(treatment_name="Knee Surgery", description="Total Knee Replacement."))
        db.session.commit()

    # Create admin if it doesn't exist
    if not User.query.filter_by(username="admin").first():
        admin_user = User(
            first_name="System", last_name="admin", username="admin", email="11d@gmail.com", role="admin"
        )
        admin_user.set_password("admin") # Use a strong password in a real app
        db.session.add(admin_user)
        db.session.commit()
    
    # Create sample doctor if it doesn't exist
    if not User.query.filter_by(username="doctor").first():
        cardiology_dept = Department.query.filter_by(name="Cardiology").first()
        if cardiology_dept:
            doctor_user = User(
                first_name="doctor", last_name="doctor", username="doctor", email="doc@gmail.com", role="doctor",
                specialization_id=cardiology_dept.id
            )
            doctor_user.set_password("doctor")
            db.session.add(doctor_user)
            db.session.commit()

# Run app and create database
if __name__ == '__main__':
    with app.app_context():
        # Drop and recreate tables for easy development (Remove in production)
        # db.drop_all() 
        db.create_all()
        seed_data() # Populate with initial data

    app.run(debug=True)

