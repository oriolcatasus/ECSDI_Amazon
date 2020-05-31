# -*- coding: utf-8 -*-

from multiprocessing import Process, Queue
from string import Template
import socket
import sys
import random
import uuid
import datetime

from rdflib import Namespace, Graph, RDF
from rdflib.namespace import FOAF
from rdflib.term import Literal
from flask import Flask, request

from AgentUtil.ACLMessages import get_message_properties, build_message, send_message
from AgentUtil.FlaskServer import shutdown_server
from AgentUtil.OntoNamespaces import ACL
from AgentUtil.Agent import Agent
import requests

import logging
logging.basicConfig(level=logging.DEBUG)

import Constants.Constants as Constants

# Configuration stuff
hostname = '127.0.1.1'
port = 9002

agn = Namespace(Constants.ONTOLOGY)

# Contador de mensajes
mss_cnt = 0

# Datos del Agente

AsistenteCompra = Agent('AsistenteCompra',
                       agn.AsistenteCompra,
                       'http://%s:%d/comm' % (hostname, port),
                       'http://%s:%d/Stop' % (hostname, port))

# Directory agent address
DirectoryAgent = Agent('DirectoryAgent',
                       agn.Directory,
                       'http://%s:9000/Register' % hostname,
                       'http://%s:9000/Stop' % hostname)


# Global triplestore graph
dsgraph = Graph()

cola1 = Queue()

# Flask stuff
app = Flask(__name__)


@app.route("/comm")
def comunicacion():
    """
    Entrypoint de comunicacion
    """
    req = Graph()
    req.parse(data=request.args['content'])
    message_properties = get_message_properties(req)
    content = message_properties['content']
    accion = str(req.value(subject=content, predicate=RDF.type))
    logging.info('Accion: ' + accion)
    if accion == 'Buscar_Productos':
        return buscar_productos(req, content)
    elif accion == 'Comprar':
        return comprar(req, content)
    elif accion == 'Informar_Envio_Iniciado':
        return informar_envio_iniciado(req, content)
    elif accion == 'Buscar_Productos_Usuario':
        return buscar_productos_usuario(req, content)
    elif accion == 'Devolver':
        return devolver(req,content)
    
    
def comprar(req, content):
    global mss_cnt
    
    mss_cnt = mss_cnt + 1
    # datos historial compra
    historial_compras = Graph()
    try:
        historial_compras.parse('./data/historial_compras.owl')
    except Exception as e:
        logging.info('No historial_compras found, creating a new one')    
    # Graph message
    cl_graph = Graph()
    cl_graph.add((content, RDF.type, Literal('Empezar_Envio_Compra')))
    # ID compra
    id_compra = uuid.uuid4().int
    str_id_compra = str(id_compra)
    logging.info('id compra: ' + str_id_compra)
    compra = agn['compra_' + str_id_compra]
    literal_id_compra = Literal(id_compra)
    historial_compras.add((compra, RDF.type, agn.compra))
    historial_compras.add((compra, agn.id, literal_id_compra))
    cl_graph.add((content, agn.id_compra, literal_id_compra))
    # codigo postal
    codigo_postal = req.value(subject=content, predicate=agn.codigo_postal)
    logging.info('codigo postal: ' + codigo_postal)
    cl_graph.add((content, agn.codigo_postal, codigo_postal))
    historial_compras.add((compra, agn.codigo_postal, codigo_postal))
    # direccion
    direccion = req.value(subject=content, predicate=agn.direccion)
    logging.info('direccion: ' + direccion)
    cl_graph.add((content, agn.direccion, direccion))
    historial_compras.add((compra, agn.direccion, direccion))
    # id usuario
    id_usuario = req.value(subject=content, predicate=agn.id_usuario)
    logging.info('id usuario: ' + id_usuario)
    cl_graph.add((content, agn.id_usuario, id_usuario))
    historial_compras.add((compra, agn.id_usuario, id_usuario))
    # tarjeta bancaria
    tarjeta_bancaria = req.value(subject=content, predicate=agn.tarjeta_bancaria)
    logging.info('tarjeta_bancaria: ' + tarjeta_bancaria)
    historial_compras.add((compra, agn.tarjeta_bancaria, tarjeta_bancaria))
    # prioridad envio
    prioridad_envio = int(req.value(subject=content, predicate=agn.prioridad_envio))
    logging.info('priodad envio: ' + str(prioridad_envio))
    cl_graph.add((content, agn.prioridad_envio, Literal(prioridad_envio)))
    historial_compras.add((compra, agn.prioridad_envio, Literal(prioridad_envio)))
    # fecha de compra
    fecha_compra = datetime.date.today()
    logging.info('fecha de compra: ' + str(fecha_compra))
    historial_compras.add((compra, agn.fecha_compra, Literal(fecha_compra)))
    # productos
    total_precio = 0
    total_peso = 0.0
    for item in req.subjects(RDF.type, agn.product):
        nombre = str(req.value(subject=item, predicate=agn.nombre))
        producto = get_producto(nombre)
        total_precio += int(producto['precio'])
        total_peso += float(producto['peso'])
        logging.info(nombre)
        producto_compra = agn[nombre + '_' + str(uuid.uuid4().int)]
        #historial_compras.add((producto_compra, RDF.type, agn.product))
        #historial_compras.add((producto_compra, agn.nombre, Literal(nombre)))
        #historial_compras.add((producto_compra, agn.id_compra, literal_id_compra))
        historial_compras.add((compra, agn.product, Literal(nombre)))
        cl_graph.add((producto_compra, RDF.type, agn.product))
        cl_graph.add((producto_compra, agn.nombre, Literal(nombre)))
    logging.info('Total precio: ' + str(total_precio))
    logging.info('Total peso: ' + str(total_peso))
    cl_graph.add((content, agn.total_peso, Literal(total_peso)))
    historial_compras.add((compra, agn.precio, Literal(total_precio)))
    historial_compras.serialize('./data/historial_compras.owl')
    # Enviar mensaje
    centro_logistico = AsistenteCompra.directory_search(DirectoryAgent, agn.CentroLogistico)
    message = build_message(
        cl_graph,
        perf=Literal('request'),
        sender=AsistenteCompra.uri,
        receiver=centro_logistico.uri,
        msgcnt=mss_cnt,
        content=content
    )
    send_message(message, centro_logistico.address)    
    return Graph().serialize(format='xml')


def buscar_productos(req, content):    
    req_dict = {}
    if req.value(subject=content, predicate=agn['min_precio']):
        req_dict['min_precio'] = req.value(subject=content, predicate=agn['min_precio'])
        logging.info('Min precio: ' + req_dict['min_precio'])    
    if req.value(subject=content, predicate=agn['max_precio']):
        req_dict['max_precio'] = req.value(subject=content, predicate=agn['max_precio'])
        logging.info('Max precio: ' + req_dict['max_precio'])    
    if req.value(content, agn.nombre):
        req_dict['nombre'] = req.value(content, agn.nombre)
        logging.info('Nombre: ' + req_dict['nombre'])
    if req.value(content, agn.tieneMarca):
        req_dict['tieneMarca'] = req.value(content, agn.tieneMarca)
        logging.info('Marca: ' + req_dict['tieneMarca'])
    if req.value(content, agn.tipo):
        req_dict['tipo'] = req.value(content, agn.tipo)
        logging.info('Tipo: ' + req_dict['tipo'])
    return build_response(**req_dict)


def build_response(tieneMarca='', min_precio=0, max_precio=sys.float_info.max, tipo='', nombre=''):
    productos = Graph().parse('./data/product.owl')
    sparql_query = Template('''
        SELECT DISTINCT ?producto ?nombre ?precio ?peso ?tieneMarca ?tipo
        WHERE {
            ?producto rdf:type ?tipo .
            ?producto pontp:nombre ?nombre .
            ?producto pontp:precio ?precio .
            ?producto pontp:peso ?peso .
            ?producto pontp:tieneMarca ?tieneMarca .
            FILTER (
                ?precio >= $min_precio && 
                ?precio <= $max_precio
            )
            FILTER CONTAINS (lcase(?nombre), '$nombre')
            FILTER CONTAINS (lcase(str(?tipo)), '$tipo')
            FILTER CONTAINS (lcase(str(?tieneMarca)), '$tieneMarca')
        }
    ''').substitute(dict(
        min_precio = min_precio,
        max_precio = max_precio,
        nombre = nombre,
        tieneMarca = tieneMarca,
        tipo = tipo
    ))
    result = productos.query(
        sparql_query,
        initNs=dict(
            rdf=RDF,
            pontp=Namespace("http://www.products.org/ontology/property/")
    ))
    result_message = Graph()
    for x in result:
        result_message.add((x.producto, RDF.type, Literal(x.tipo)))
        result_message.add((x.producto, agn.nombre, x.nombre))
        result_message.add((x.producto, agn.peso, x.peso))
        result_message.add((x.producto, agn.precio, x.precio))
        result_message.add((x.producto, agn.tieneMarca, Literal(x.tieneMarca)))
    return result_message.serialize(format='xml')

def get_producto(nombre):
    productos = Graph().parse('./data/product.owl')
    sparql_query = Template('''
        SELECT ?producto ?nombre ?precio ?peso ?tieneMarca
        WHERE {
            ?producto rdf:type ?type_prod .
            ?producto pontp:nombre ?nombre .
            ?producto pontp:precio ?precio .
            ?producto pontp:peso ?peso .
            ?producto pontp:tieneMarca ?tieneMarca .
            FILTER (
                ?nombre = '$nombre' 
            )
        }
    ''').substitute(dict(
        nombre = nombre
    ))
    result = productos.query(
        sparql_query,
        initNs=dict(
            rdf=RDF,
            pontp=Namespace("http://www.products.org/ontology/property/")
        )
    )
    producto = next(iter(result))
    logging.info(producto)
    return dict(
        precio=producto.precio,
        peso=producto.peso,
        tieneMarca=producto.tieneMarca
    )


def informar_envio_iniciado(req, content):
    global mss_cnt
    
    mss_cnt = mss_cnt + 1
    logging.info('Envio iniciado')
    id_compra = int(req.value(content, agn.id_compra))
    literal_id_compra = Literal(id_compra)
    logging.info('id compra: ' + literal_id_compra)
    fecha_recepcion = req.value(content, agn.fecha_recepcion)
    logging.info('fecha de recepcion del envio: ' + fecha_recepcion)
    transportista = req.value(content, agn.transportista)
    logging.info('transportista: ' + transportista)
    # Hacemos la factura
    graph = Graph()
    factura = agn['factura_' + str(mss_cnt)]
    graph.add((factura, RDF.type, Literal('factura')))
    graph.add((factura, agn.id_compra, literal_id_compra))
    graph.add((factura, agn.fecha_recepcion, fecha_recepcion))
    graph.add((factura, agn.transportista, transportista))
    # Buscamos todos los productos de la compra
    historial_compras = Graph().parse('./data/historial_compras.owl')
    productos = Graph().parse('./data/product.owl')
    subject = next(historial_compras.subjects(agn.id, literal_id_compra))
    # id usuario
    id_usuario = historial_compras.value(subject, agn.id_usuario)
    logging.info('id usuario: ' + id_usuario)
    graph.add((factura, agn.id_usuario, id_usuario))
    # prioridad envio
    prioridad_envio = int(historial_compras.value(subject, agn.prioridad_envio))
    logging.info('prioridad envio: ' + str(prioridad_envio))
    graph.add((factura, agn.prioridad_envio, Literal(prioridad_envio)))
    # Direccion
    direccion = historial_compras.value(subject, agn.direccion)
    logging.info('direccion: ' + direccion)
    graph.add((factura, agn.direccion, direccion))
    # Codigo postal
    cp = historial_compras.value(subject, agn.codigo_postal)
    logging.info('codigo postal: ' + cp)
    graph.add((factura, agn.codigo_postal, cp))
    # Fecha de compra
    fecha_compra = historial_compras.value(subject, agn.fecha_compra)
    logging.info('fecha de compra: ' + str(fecha_compra))
    graph.add((factura, agn.fecha_compra, fecha_compra))
    # Productos
    i = 1
    for producto in historial_compras.objects(subject, agn.product):
        logging.info('Producto:')
        logging.info('nombre: ' + producto)
        subject_producto = agn[producto + '_' + str(i)]
        graph.add((subject_producto, RDF.type, agn.product))
        graph.add((subject_producto, agn.nombre, producto))
        datos_producto = get_producto(producto)
        precio = datos_producto['precio']
        logging.info('precio: ' + precio)
        graph.add((subject_producto, agn.precio, Literal(precio)))
        marca = datos_producto['tieneMarca'].split('/')[5]
        logging.info('marca: ' + marca)
        graph.add((subject_producto, agn.tieneMarca, Literal(marca)))
        i += 1
    # Precio total
    precio_total = int(historial_compras.value(subject, agn.precio))
    if prioridad_envio > 0:
        precio_total += 10
    #enviar accion pagador
    logging.info("Abans del caos")
    tarjeta_bancaria = int(historial_compras.value(subject, agn.tarjeta_bancaria))
    logging.info("C mamó")
    Pagador = AsistenteCompra.directory_search(DirectoryAgent, agn.Pagador)
    logging.info("Estamos chill")
    gCobrar = Graph()
    cobrar = agn['cobrar_' + str(mss_cnt)]
    gCobrar.add((cobrar, RDF.type, Literal('Cobrar')))
    gCobrar.add((cobrar, agn.tarjeta_bancaria, Literal(tarjeta_bancaria)))
    gCobrar.add((cobrar, agn.precio_total, Literal(precio_total)))
    message = build_message(
        gCobrar,
        perf=Literal('request'),
        sender=AsistenteCompra.uri,
        receiver=Pagador.uri,
        msgcnt=mss_cnt,
        content=cobrar
    )
    logging.info("Abans d'enviar")
    Pagado_correctamente = send_message(message, Pagador.address)
    for item in Pagado_correctamente.subjects(RDF.type, Literal('RespuestaCobro')):
        for RespuestaCobro in Pagado_correctamente.objects(item, agn.respuesta_cobro):
            logging.info(str(RespuestaCobro))
    logging.info("cobro rebut")
    #afegir factura
    graph.add((factura, agn.precio_total, Literal(precio_total)))
    # Enviar mensaje
    agente_ext_usuario = AsistenteCompra.directory_search(DirectoryAgent, agn.AgenteExtUsuario)
    message = build_message(
        graph,
        perf=Literal('request'),
        sender=AsistenteCompra.uri,
        receiver=agente_ext_usuario.uri,
        msgcnt=mss_cnt,
        content=factura
    )
    send_message(message, agente_ext_usuario.address) 
    return Graph().serialize(format='xml')


def buscar_productos_usuario(req, content):
    id_usuario = req.value(subject=content, predicate=agn['id_usuario'])
    logging.info(id_usuario)      
    return build_response_devolver(id_usuario)


def build_response_devolver(id_usuario):
    historial_compras = Graph().parse('./data/historial_compras.owl')
    logging.info("ID Usuario en la busqueda " + id_usuario)
    sparql_query = Template('''
        SELECT DISTINCT ?compra ?product ?id ?id_usuario
        WHERE {
            ?compra rdf:type ?type_prod .
            ?compra ns:product ?product .
            ?compra ns:id_usuario ?id_usuario .
            ?compra ns:id ?id .
            FILTER (
                ?id_usuario = '$id_usuario'
            )
        }
    ''').substitute(dict(
        id_usuario = id_usuario
    ))
    result = historial_compras.query(
        sparql_query,
        initNs=dict(
            rdf=RDF,
            ns=agn,
    ))
    i = 0
    result_message = Graph()
    for x in result:
        producto = agn[x.product + '_' + i]
        result_message.add((producto, RDF.type, agn.product))
        result_message.add((producto, agn.nombre, x.product))
        result_message.add((producto, agn.id_compra, x.id))
        i = i + 1
    return result_message.serialize(format='xml')

def devolver(req, content):
    logging.info('Empezamos devolucion')
    id_usuario = req.value(subject=content, predicate=agn.id_usuario)
    logging.info('ID Usuario devolucion = ' + id_usuario)
    motivo = str(req.value(subject=content, predicate=agn.motivo))
    logging.info('Motivo devolucion = ' + motivo)
    nombre = req.value(subject=content, predicate=agn.producto)
    logging.info('Nombre producto de devolucion = ' + str(nombre))
    id_compra = req.value(subject=content, predicate=agn.id_compra)
    logging.info('ID Compra de producto de devolucion = ' + str(id_compra))
    tarjeta = req.value(subject=content, predicate=agn.tarjeta)
    logging.info('Tarjeta del cliente = ' + str(tarjeta))

    resultado = 'null'
    precio = 0

    if motivo == 'equivocado':
        resultado = 'Devolucion por equivocacion'
        precio = int(get_producto(nombre)['precio'])
    elif motivo == 'defectuoso':
        prob_dev = random.randint(0, 100)
        if prob_dev < 90:
            resultado = 'Devolucion por producto defectuoso'
            precio = int(get_producto(nombre)['precio'])
        else:
            resultado = 'Devolucion rechazada'
    else:
        prob_dev = random.randint(0, 100)
        if prob_dev < 70:
            resultado = 'Devolucion por producto que no satisface las necesidades del comprador'
            precio = int(get_producto(nombre)['precio'])
        else:
            resultado = 'Devolucion rechazada'
    logging.info('Resultado: ' + resultado)

    result_message = Graph()
    respuesta = agn['respuesta' + str(mss_cnt)]
    result_message.add((respuesta, RDF.type, agn.respuesta))
    result_message.add((respuesta, agn.resultado, Literal(resultado)))

    if precio > 0:
        id_compra_elim = agn['compra_' + str(id_compra)]
        logging.info(id_compra_elim)
        historial_compras = Graph().parse('./data/historial_compras.owl')
        historial_compras.remove((id_compra_elim, agn.product, Literal(nombre)))
        historial_compras.serialize('./data/historial_compras.owl')

        Pagador = AsistenteCompra.directory_search(DirectoryAgent, agn.Pagador)
        gCobrar = Graph()
        cobrar = agn['pagar_' + str(mss_cnt)]
        gCobrar.add((cobrar, RDF.type, Literal('Pagar')))
        gCobrar.add((cobrar, agn.tarjeta_bancaria, Literal(tarjeta)))
        gCobrar.add((cobrar, agn.precio_total, Literal(precio)))
        message = build_message(
            gCobrar,
            perf=Literal('request'),
            sender=AsistenteCompra.uri,
            receiver=Pagador.uri,
            msgcnt=mss_cnt,
            content=cobrar
        )
        Pagado_correctamente = send_message(message, Pagador.address)
        for item in Pagado_correctamente.subjects(RDF.type, Literal('RespuestaPago')):
            for RespuestaCobro in Pagado_correctamente.objects(item, agn.respuesta_cobro):
                logging.info(str(RespuestaCobro))
        logging.info("pago realizado")

    return result_message.serialize(format='xml')

@app.route("/Stop")
def stop():
    """
    Entrypoint que para el agente

    :return:
    """
    tidyup()
    shutdown_server()
    return "Parando Servidor"


def tidyup():
    """
    Acciones previas a parar el agente

    """
    pass


def agentbehavior1(cola):
    """
    Un comportamiento del agente

    :return:
    """
    AsistenteCompra.register_agent(DirectoryAgent)
    pass


if __name__ == '__main__':
    # Ponemos en marcha los behaviors
    ab1 = Process(target=agentbehavior1, args=(cola1,))
    ab1.start()

    # Ponemos en marcha el servidor
    app.run(host=hostname, port=port)

    # Esperamos a que acaben los behaviors
    ab1.join()
    print('The End')


