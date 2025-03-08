-- setup_db.sql
-- Створення бази даних та таблиці для зберігання даних про комп'ютерні комплектуючі

CREATE DATABASE IF NOT EXISTS computer_parts_db;
USE computer_parts_db;

CREATE TABLE IF NOT EXISTS components (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    type VARCHAR(100) NOT NULL,
    description TEXT,
    price DECIMAL(10,2),
    specs TEXT
);

INSERT INTO components (name, type, description, price, specs) VALUES
('Intel Core i7-12700K', 'CPU', '12th Gen Intel processor with 12 cores', 350.00, '{"cores":12, "threads":20, "base_clock":"3.6GHz"}'),
('AMD Ryzen 7 5800X', 'CPU', '8-core AMD processor with high performance', 299.00, '{"cores":8, "threads":16, "base_clock":"3.8GHz"}'),
('NVIDIA GeForce RTX 3080', 'GPU', 'High-end graphics card for gaming', 699.00, '{"memory":"10GB", "clock":"1440MHz"}'),
('Corsair Vengeance LPX 16GB', 'RAM', 'High performance DDR4 memory kit', 80.00, '{"capacity":"16GB", "speed":"3200MHz"}'),
('Samsung 970 EVO Plus 1TB', 'SSD', 'High-speed NVMe SSD for fast storage', 150.00, '{"capacity":"1TB", "read_speed":"3500MB/s"}');
