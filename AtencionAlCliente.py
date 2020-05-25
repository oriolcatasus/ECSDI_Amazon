# -*- coding: utf-8 -*-

from multiprocessing import Process, Queue
from string import Template
import socket
import sys
import uuid

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

AtencionAlCliente = Agent('AtencionAlCliente',
                       agn.AtencionAlCliente,
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
    historial_compras.add((compra, agn.id_usuario, id_usuario))
    # tarjeta bancaria
    tarjeta_bancaria = req.value(subject=content, predicate=agn.tarjeta_bancaria)
    logging.info('tarjeta_bancaria: ' + tarjeta_bancaria)
    historial_compras.add((compra, agn.tarjeta_bancaria, tarjeta_bancaria))
    # prioridad envio
    prioridad_envio = int(req.value(subject=content, predicate=agn.prioridad_envio))
    logging.info('priodad envio: ' + str(prioridad_envio))
    cl_graph.add((content, agn.prioridad_envio, Literal(prioridad_envio)))
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
    centro_logistico = AtencionAlCliente.directory_search(DirectoryAgent, agn.CentroLogistico)
    message = build_message(
        cl_graph,
        perf=Literal('request'),
        sender=AtencionAlCliente.uri,
        receiver=centro_logistico.uri,
        msgcnt=mss_cnt,
        content=content
    )
    send_message(message, centro_logistico.address)    
    return Graph().serialize(format='xml')


def buscar_productos(req, content):    
    req_dict = {}
    if req.value(subject=content, predicate=agn['min_precio']):
        logging.info('Entra MIN precio')
        req_dict['min_precio'] = req.value(subject=content, predicate=agn['min_precio'])
        logging.info(req_dict['min_precio'])    
    if req.value(subject=content, predicate=agn['max_precio']):
        logging.info('Entra MAX precio')
        req_dict['max_precio'] = req.value(subject=content, predicate=agn['max_precio'])
        logging.info(req_dict['max_precio'])    
    return build_response(**req_dict)


def build_response(tieneMarca='(.*)', min_precio=0, max_precio=sys.float_info.max):
    productos = Graph().parse('./data/product.owl')

    sparql_query = Template('''
        SELECT DISTINCT ?producto ?nombre ?precio ?peso ?tieneMarca
        WHERE {
            ?producto rdf:type ?type_prod .
            ?producto pontp:nombre ?nombre .
            ?producto pontp:precio ?precio .
            ?producto pontp:peso ?peso .
            ?producto pontp:tieneMarca ?tieneMarca .
            FILTER (
                ?precio > $min_precio && 
                ?precio < $max_precio
            )
        }
    ''').substitute(dict(
        min_precio=min_precio,
        max_precio=max_precio
    ))
    result = productos.query(
        sparql_query,
        initNs=dict(
            foaf=FOAF,
            rdf=RDF,
            ns=agn,
            pontp=Namespace("http://www.products.org/ontology/property/")
        )
    )

    result_message = Graph()
    for x in result:
        result_message.add((x.producto, RDF.type, agn.product))
        result_message.add((x.producto, agn.nombre, x.nombre))
        result_message.add((x.producto, agn.peso, x.peso))
        result_message.add((x.producto, agn.precio, x.precio))
        result_message.add((x.producto, agn.tieneMarca, Literal(x.tieneMarca.split('/')[5])))

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
            ?producto pontp:tieneMarca ?tieneMarca
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
    #enviar accion pagador
    logging.info("Abans del caos")
    tarjeta_bancaria = int(historial_compras.value(subject, agn.tarjeta_bancaria))
    logging.info("C mamó")
    Pagador = AtencionAlCliente.directory_search(DirectoryAgent, agn.Pagador)
    logging.info("Estamos chill")
    gCobrar = Graph()
    cobrar = agn['cobrar_' + str(mss_cnt)]
    gCobrar.add((cobrar, RDF.type, Literal('Cobrar')))
    gCobrar.add((cobrar, agn.tarjeta_bancaria, Literal(tarjeta_bancaria)))
    gCobrar.add((cobrar, agn.precio_total, Literal(precio_total)))
    message = build_message(
        gCobrar,
        perf=Literal('request'),
        sender=AtencionAlCliente.uri,
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
    agente_ext_usuario = AtencionAlCliente.directory_search(DirectoryAgent, agn.AgentExtUser)
    message = build_message(
        graph,
        perf=Literal('request'),
        sender=AtencionAlCliente.uri,
        receiver=agente_ext_usuario.uri,
        msgcnt=mss_cnt,
        content=factura
    )
    send_message(message, agente_ext_usuario.address) 
    return Graph().serialize(format='xml')


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
    AtencionAlCliente.register_agent(DirectoryAgent)
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


