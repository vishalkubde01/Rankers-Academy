from django.urls import path
from . import views

urlpatterns = [
    path('', views.attendance, name='attendance'),
    path('mark/', views.mark_attendance, name='mark_attendance'),
    path('student/<int:student_id>/', views.view_student_attendance, name='view_student_attendance'),
    path('my-attendance/', views.my_attendance, name='my_attendance'),

]
